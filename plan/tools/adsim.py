"""Bit-faithful Python re-implementation of AntiDupl's reduced-image + SSIM pipeline.

Mirrors (as of upstream commit e06d082, v2.3.13):
  src/AntiDupl/adDataCollector.cpp  TDataCollector::FillPixelData
      decode -> view labelled Bgra32 -> Simd::BgraToGray
      -> Simd::Resize (bilinear, default method) to 256x256
      -> Simd::ReduceGray2x2 down to reducedImageSize (128x128)
  src/AntiDupl/adImageComparer.cpp  TImageComparer_SSIM::IsDuplPair
      global (single-window) SSIM over the 128x128 plane, float32 arithmetic

Used to reproduce the numbers AntiDupl shows in the "Difference" column.
Decoding uses Pillow (libjpeg-turbo, ISLOW IDCT), i.e. what AntiDupl's
TurboJPEG path decodes; the GDI+ path is assumed to decode the same pixels
(the reproduced values match AntiDupl's to all displayed digits).
"""
import numpy as np
from PIL import Image

# Simd BgrToGray weights: int(w * (1 << 14) + 0.5)
B_W, G_W, R_W = 1868, 9617, 4899


def bgr_to_gray(b, g, r):
    return ((B_W * b.astype(np.int64) + G_W * g.astype(np.int64) + R_W * r.astype(np.int64) + 8192) >> 14).astype(np.uint8)


def gray_correct(rgb):
    """Correct conversion (GDI+ path, or TurboJPEG after the TJPF_BGRA fix)."""
    return bgr_to_gray(rgb[..., 2], rgb[..., 1], rgb[..., 0])


def gray_turbo_swapped(rgb):
    """Current TurboJPEG path: tjDecompress2(TJPF_RGBA) writes R,G,B,A bytes into a
    view labelled Bgra32, so BgraToGray reads R as blue and B as red."""
    return bgr_to_gray(rgb[..., 0], rgb[..., 1], rgb[..., 2])


def _estimate_index_alpha(src_size, dst_size):
    """Simd::Base::ResizerByteBilinear::EstimateIndexAlpha (float32 math, FRACTION_RANGE=16)."""
    scale = np.float32(src_size) / np.float32(dst_size)
    idx = np.empty(dst_size, np.int64)
    alp = np.empty(dst_size, np.int64)
    for i in range(dst_size):
        a = np.float32((np.float32(i) + np.float32(0.5)) * scale - np.float32(0.5))
        index = int(np.floor(a))
        a = np.float32(a - np.float32(index))
        if index < 0:
            index, a = 0, np.float32(0)
        if index > src_size - 2:
            index, a = src_size - 2, np.float32(1)
        idx[i] = index
        alp[i] = int(np.float32(a * np.float32(16) + np.float32(0.5)))
    return idx, alp


def resize_bilinear(gray, dw, dh):
    """Simd::Base::ResizerByteBilinear::Run for 1 channel (LINEAR_SHIFT=4, BILINEAR_SHIFT=8)."""
    sh, sw = gray.shape
    if (sw, sh) == (dw, dh):
        return gray.copy()
    ix, ax = _estimate_index_alpha(sw, dw)
    iy, ay = _estimate_index_alpha(sh, dh)
    g = gray.astype(np.int64)

    def hrow(r):
        t = g[r, ix]
        return (t << 4) + (g[r, ix + 1] - t) * ax

    out = np.empty((dh, dw), np.uint8)
    for dy in range(dh):
        p0, p1 = hrow(iy[dy]), hrow(iy[dy] + 1)
        out[dy] = (((p0 << 4) + (p1 - p0) * ay[dy] + 128) >> 8).astype(np.uint8)
    return out


def reduce2x2(g):
    """Simd::Base::ReduceGray2x2 for even sizes: (a+b+c+d+2)>>2."""
    x = g.astype(np.int64)
    return ((x[0::2, 0::2] + x[0::2, 1::2] + x[1::2, 0::2] + x[1::2, 1::2] + 2) >> 2).astype(np.uint8)


def reduced(gray, reduced_size=128, initial=256):
    """INITIAL_REDUCED_IMAGE_SIZE=256 bilinear, then 2x2 reductions down to reduced_size."""
    r = resize_bilinear(gray, initial, initial)
    size = initial
    while size > reduced_size:
        r = reduce2x2(r)
        size //= 2
    return r


def reduced_area(gray, reduced_size=128):
    """Proposed: area (box) resampling straight to reduced_size (SimdResizeMethodArea)."""
    return np.asarray(Image.fromarray(gray).resize((reduced_size, reduced_size), Image.BOX))


f32 = np.float32
C1 = f32((0.01 * 255) ** 2)
C2 = f32((0.03 * 255) ** 2)


def _stats(m):
    n = m.size
    s = int(m.astype(np.int64).sum())
    sq = int((m.astype(np.int64) ** 2).sum())
    avg = f32(f32(s) / f32(n))
    avg_sq = f32(f32(sq) / f32(n))
    var = f32(abs(f32(avg_sq - f32(avg * avg))))
    return avg, var


def antidupl_ssim_difference(m1, m2, pow_in_double=True):
    """Current TImageComparer_SSIM::IsDuplPair arithmetic.

    pow(float, int) resolves to the double overload under MSVC's <cmath>, so the
    denominator's first factor is double while the numerator is float -> identical
    planes can yield res slightly below 1 -> difference 7.63e-06 or 1.526e-05.
    Returns (difference_before_crc_epsilon, res).
    """
    n = m1.size
    a1, v1 = _stats(m1)
    a2, v2 = _stats(m2)
    corr = int((m1.astype(np.int64) * m2.astype(np.int64)).sum())
    sigma = f32(f32(f32(corr) / f32(n)) - f32(a1 * a2))
    num = f32(f32(f32(f32(2) * a1) * a2) + C1) * f32(f32(f32(2) * sigma) + C2)
    num = f32(num)
    if pow_in_double:
        den = (float(a1) ** 2 + float(a2) ** 2 + float(C1)) * float(f32(f32(v1 + v2) + C2))
        res = f32(float(num) / den)
    else:
        den = f32(f32(f32(a1 * a1) + f32(a2 * a2)) + C1) * f32(f32(v1 + v2) + C2)
        res = f32(num / f32(den))
    diff = float(f32(f32(100) - f32(res * f32(100))))
    return max(diff, 0.0), float(res)


def fixed_ssim_difference(m1, m2):
    """Proposed: exact 0 for identical planes, everything else in double precision."""
    if np.array_equal(m1, m2):
        return 0.0
    x = m1.astype(np.float64)
    y = m2.astype(np.float64)
    mx, my = x.mean(), y.mean()
    vx, vy = x.var(), y.var()
    cxy = (x * y).mean() - mx * my
    c1, c2 = (0.01 * 255) ** 2, (0.03 * 255) ** 2
    res = (2 * mx * my + c1) * (2 * cxy + c2) / ((mx * mx + my * my + c1) * (vx + vy + c2))
    return max(0.0, 100.0 * (1.0 - res))


def load_rgb(path):
    return np.asarray(Image.open(path).convert("RGB"))


def starts_with_jfif(path):
    """TTurboJpeg::Supported(): only files starting FF D8 FF E0 go to libjpeg-turbo."""
    with open(path, "rb") as f:
        return f.read(4) == b"\xff\xd8\xff\xe0"


def current_gray(path, rgb=None):
    """Gray plane input exactly as the current build produces it for this file."""
    rgb = load_rgb(path) if rgb is None else rgb
    return gray_turbo_swapped(rgb) if starts_with_jfif(path) else gray_correct(rgb)
