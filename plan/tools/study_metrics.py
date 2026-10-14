"""Per-image features and pair metrics of the study (plan 07), used by
settings_study.py. Every metric is a difference: 0 for identical images,
larger for more different ones (similarities are turned around).

Image features (features(), cached by settings_study.py):
    planes      AntiDupl's reduced planes, grey and B/G/R, bilinear (its
                pipeline, bit-faithful via adsim) and area, sizes 16-128
    sq256       256 x 256 RGB, area-resampled, aspect ignored like AntiDupl
    hist        HSV histogram, 8 x 8 x 8, normalised
    hashes      aHash, dHash, pHash, wHash (64 bit), pHash and dHash with
                256 bits, colorhash (from a 512 px copy), crop-resistant
                hash; with OpenCV (STUDY_PYLIB) also its block mean,
                Marr-Hildreth, radial variance and colour moment hashes
    orb, akaze  with OpenCV: ORB and AKAZE keypoints on the 512 px copy
    sift        SIFT keypoints (row, col) and descriptors on a 512 px grey
                copy, for alignment
    quality     pixels, bytes per pixel, JPEG quality estimate (from the
                quantisation tables), Laplacian sharpness at native size
and two working copies for the libjxl tools (longest side 512 and 1024),
written by settings_study.py.
"""
import os
import subprocess
import sys

import imagehash
import numpy as np
from PIL import Image
from scipy import signal
from skimage import color as skcolor
from skimage import feature as skfeature
from skimage import measure as skmeasure
from skimage import metrics as skmetrics
from skimage import transform as sktransform

import adsim

# Extra package folders (pip --target), such as OpenCV's: STUDY_PYLIB, a
# path list. Set in the environment so the worker processes get it too.
for _p in reversed(os.environ.get("STUDY_PYLIB", "").split(os.pathsep)):
    if _p and _p not in sys.path:
        sys.path.insert(0, _p)
try:
    import cv2
except ImportError:
    cv2 = None

Image.MAX_IMAGE_PIXELS = None
SIZES = [16, 32, 64, 128]
C1, C2 = (0.01 * 255) ** 2, (0.03 * 255) ** 2
# libjxl's tools (djxl, butteraugli_main, ssimulacra2): this folder, or
# PATH when the variable is unset.
LIBJXL = os.environ.get("LIBJXL", "")

# IJG standard luminance table (natural order) for the quality estimate.
STD_LUMA = np.array([16, 11, 10, 16, 24, 40, 51, 61, 12, 12, 14, 19, 26, 58, 60, 55, 14, 13, 16, 24, 40, 57, 69, 56,
                     14, 17, 22, 29, 51, 87, 80, 62, 18, 22, 37, 56, 68, 109, 103, 77, 24, 35, 55, 64, 81, 104, 113, 92,
                     49, 64, 78, 87, 103, 121, 120, 101, 72, 92, 95, 98, 112, 100, 103, 99], dtype=np.float64)


def jpeg_quality(im):
    """IJG quality (1-100) whose scaled standard luminance table is closest
    to the file's, compared as sums, so the table order doesn't matter;
    None for other formats."""
    q = getattr(im, "quantization", None)
    if not q or 0 not in q:
        return None
    total = float(np.sum(q[0]))
    best, best_err = None, None
    for quality in range(1, 101):
        scale = 5000 / quality if quality < 50 else 200 - 2 * quality
        table = np.clip(np.floor((STD_LUMA * scale + 50) / 100), 1, 255)
        err = abs(table.sum() - total)
        if best_err is None or err < best_err:
            best, best_err = quality, err
    return best


def ijg_quality_of_scale(scale):
    """The IJG quality whose table scaling is `scale` per cent."""
    return float(np.clip(5000 / scale if scale > 100 else (200 - scale) / 2, 1, 100))


# Low-frequency AC positions (row, column) of the 8 x 8 DCT, in zigzag
# order: the ones a JPEG quantises coarsely enough to leave a trace and
# that still hold enough non-zero coefficients.
HISTORY_POSITIONS = [(0, 1), (1, 0), (2, 0), (1, 1), (0, 2), (0, 3), (1, 2), (2, 1), (3, 0), (4, 0), (3, 1),
                     (2, 2), (1, 3), (0, 4)]


def jpeg_history(path, side=1536):
    """The IJG quality of the strongest JPEG compression the pixels went
    through, whatever the file's format is now; None when no JPEG trace
    shows. Returns (quality, positions that showed a step).

    A JPEG stores each 8 x 8 block's DCT coefficients rounded to multiples
    of the quantisation table's steps; decoding and even re-saving at a
    finer step keep them near those multiples (Fan and de Queiroz 2003).
    On a central crop of the luma: the block grid is where the jumps
    between neighbouring pixels peak every 8 pixels (a crop shifts it),
    then per coefficient position the largest step q with cos(2 pi D / q)
    averaging over 0.6 for the coefficients D away from zero, then the
    IJG quality whose table scaling fits those steps (the median)."""
    from scipy import fft
    im = open_image(path).convert("RGB")
    rgb = np.asarray(im, dtype=np.float64)
    h, w = rgb.shape[:2]
    y0, x0 = max(0, (h - side) // 2), max(0, (w - side) // 2)
    rgb = rgb[y0:y0 + side, x0:x0 + side]
    luma = rgb @ np.array([0.299, 0.587, 0.114])
    # Grid: the column (row) where blocks start is the one with the largest
    # average step from the pixel before it, counted every 8 pixels.
    jx = np.abs(np.diff(luma, axis=1)).mean(axis=0)
    jy = np.abs(np.diff(luma, axis=0)).mean(axis=1)
    ox = int(np.argmax([jx[(np.arange(len(jx)) + 1) % 8 == c].mean() for c in range(8)]))
    oy = int(np.argmax([jy[(np.arange(len(jy)) + 1) % 8 == c].mean() for c in range(8)]))
    ny, nx = (luma.shape[0] - oy) // 8, (luma.shape[1] - ox) // 8
    blocks = luma[oy:oy + 8 * ny, ox:ox + 8 * nx].reshape(ny, 8, nx, 8).transpose(0, 2, 1, 3)
    # Clipped pixels (pure white or black) break the relation to the steps.
    keep = (blocks.min(axis=(2, 3)) > 2) & (blocks.max(axis=(2, 3)) < 253)
    coefs = fft.dctn(blocks[keep] - 128, axes=(1, 2), norm="ortho")
    scales = []
    for r, c in HISTORY_POSITIONS:
        d = coefs[:, r, c]
        best = None
        for q in range(2, 121):
            sel = d[np.abs(d) >= q / 2]
            if len(sel) < 30:
                break
            if np.cos(2 * np.pi * sel / q).mean() >= 0.6:
                best = q
        if best is not None:
            scales.append(100 * best / STD_LUMA[r * 8 + c])
    if len(scales) < 3:
        return None, len(scales)
    return round(ijg_quality_of_scale(float(np.median(scales))), 1), len(scales)


def open_image(path):
    """Pillow's image of the file; JPEG XL, which Pillow can't read, through
    libjxl's djxl."""
    if not path.lower().endswith(".jxl"):
        return Image.open(path)
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        out = os.path.join(tmp, "decoded.png")
        subprocess.run([os.path.join(LIBJXL, "djxl.exe"), path, out, "--quiet"], check=True, capture_output=True)
        im = Image.open(out)
        im.load()
        return im


def longest(im, side):
    if max(im.size) <= side:
        return im.copy()
    f = side / max(im.size)
    return im.resize((max(1, round(im.width * f)), max(1, round(im.height * f))), Image.BOX)


HASHES = ("ahash", "dhash", "phash", "whash", "colorhash", "phash-256", "dhash-256")


def hashes(small):
    """The perceptual hashes of a 512 px copy: 64 bits, and pHash and dHash
    also with 256 bits, the size of Meta's PDQ hash."""
    return {"ahash": imagehash.average_hash(small).hash.flatten(), "dhash": imagehash.dhash(small).hash.flatten(),
            "phash": imagehash.phash(small).hash.flatten(), "whash": imagehash.whash(small).hash.flatten(),
            "colorhash": imagehash.colorhash(small).hash.flatten(),
            "phash-256": imagehash.phash(small, hash_size=16).hash.flatten(),
            "dhash-256": imagehash.dhash(small, hash_size=16).hash.flatten()}


CV_HASHES = ("cv-blockmean", "cv-marrhildreth", "cv-radialvariance", "cv-colormoment")
_hashers = {}


def cv_hasher(name):
    if name not in _hashers:
        h = cv2.img_hash
        _hashers[name] = {"cv-blockmean": h.BlockMeanHash_create, "cv-marrhildreth": h.MarrHildrethHash_create,
                          "cv-radialvariance": h.RadialVarianceHash_create,
                          "cv-colormoment": h.ColorMomentHash_create}[name]()
    return _hashers[name]


# Features added after the first study; late_features() fills them into
# caches made before.
LATE_KEYS = ("hashes", "cvhash", "orb", "akaze")


def late_features(small):
    """The hashes, OpenCV's hashes, and ORB and AKAZE keypoints ((x, y)
    and binary descriptors) of a 512 px copy; the OpenCV ones None
    without OpenCV."""
    out = {"hashes": hashes(small), "cvhash": None, "orb": None, "akaze": None}
    if cv2 is None:
        return out
    bgr = np.ascontiguousarray(np.asarray(small.convert("RGB"))[..., ::-1])
    out["cvhash"] = {name: cv_hasher(name).compute(bgr) for name in CV_HASHES}
    grey = np.asarray(small.convert("L"))
    # OpenCV 5 moved AKAZE to the contrib module xfeatures2d.
    akaze = cv2.AKAZE_create() if hasattr(cv2, "AKAZE_create") else cv2.xfeatures2d.AKAZE_create()
    for name, detector in (("orb", cv2.ORB_create(nfeatures=1000)), ("akaze", akaze)):
        kp, desc = detector.detectAndCompute(grey, None)
        out[name] = (np.array([k.pt for k in kp], dtype=np.float32).reshape(-1, 2), desc)
    return out


def needs_late(cached):
    if any(k not in cached for k in LATE_KEYS) or set(HASHES) - set(cached["hashes"]):
        return True
    return cv2 is not None and cached["orb"] is None


def features(path):
    im = open_image(path)
    quality = jpeg_quality(im)
    im = im.convert("RGB")
    rgb = np.asarray(im)
    gray = adsim.gray_correct(rgb)
    planes = {}
    for colour, chans in (("gray", [gray]), ("colour", [rgb[..., 2], rgb[..., 1], rgb[..., 0]])):
        bil = [adsim.resize_bilinear(np.ascontiguousarray(c), 256, 256) for c in chans]
        size = 256
        while size > SIZES[0]:
            bil = [adsim.reduce2x2(p) for p in bil]
            size //= 2
            if size in SIZES:
                planes[(colour, "bilinear", size)] = np.stack(bil)
        for s in SIZES:
            planes[(colour, "area", s)] = np.stack([np.asarray(Image.fromarray(np.ascontiguousarray(c)).resize((s, s), Image.BOX))
                                                    for c in chans])
    sq256 = np.asarray(im.resize((256, 256), Image.BOX))
    hsv = np.asarray(im.resize((256, 256), Image.BOX).convert("HSV")).reshape(-1, 3) // 32
    hist = np.bincount(hsv[:, 0] * 64 + hsv[:, 1] * 8 + hsv[:, 2], minlength=512).astype(np.float64)
    hist /= hist.sum()
    small = longest(im, 512)
    crh = imagehash.crop_resistant_hash(small)
    g512 = np.asarray(small.convert("L"), dtype=np.float64) / 255
    try:
        sift = skfeature.SIFT(n_octaves=4, n_scales=3)
        sift.detect_and_extract(g512)
        keys, desc = sift.keypoints.astype(np.float32), sift.descriptors
        if len(keys) > 800:
            order = np.argsort(-sift.scales)[:800] if hasattr(sift, "scales") else np.arange(800)
            keys, desc = keys[order], desc[order]
    except RuntimeError:
        keys, desc = np.zeros((0, 2), np.float32), np.zeros((0, 128), np.uint8)
    lap = gray.astype(np.float64)
    lap = lap[1:-1, 1:-1] * 4 - lap[:-2, 1:-1] - lap[2:, 1:-1] - lap[1:-1, :-2] - lap[1:-1, 2:]
    out = {
        "planes": planes, "sq256": sq256, "hist": hist, "crh": crh,
        "sift_keys": keys, "sift_desc": desc, "sift_shape": g512.shape,
        "pixels": rgb.shape[0] * rgb.shape[1], "shape": rgb.shape[:2],
        "bpp": os.path.getsize(path) / (rgb.shape[0] * rgb.shape[1]),
        "jpeg_quality": quality, "sharpness": float(lap.var()),
    }
    out.update(late_features(small))
    return out


# ---------------------------------------------------------------- metrics


def antidupl_ssim(a, b):
    """AntiDupl's global SSIM per plane (exact arithmetic), averaged."""
    out = 0.0
    for x, y in zip(a.astype(np.float64), b.astype(np.float64)):
        mx, my = x.mean(), y.mean()
        vx, vy = x.var(), y.var()
        cov = (x * y).mean() - mx * my
        res = (2 * mx * my + C1) * (2 * cov + C2) / ((mx * mx + my * my + C1) * (vx + vy + C2))
        out += max(0.0, 100.0 * (1.0 - res))
    return out / len(a)


def antidupl_msd(a, b):
    d = a.astype(np.float64) - b.astype(np.float64)
    return float(np.sqrt((d * d).mean()) / 255 * 100)


def colour_block(a, b):
    d2 = ((a.astype(np.float64) - b.astype(np.float64)) ** 2).mean(axis=0)
    s = d2.shape[0] // 4
    return float(np.sqrt(d2.reshape(s, 4, s, 4).mean(axis=(1, 3)).max()) / 255 * 100)


def windowed_ssim(a, b, colour):
    """skimage SSIM (7 x 7 Gaussian windows) on 256 x 256: 100 x (1 - mean)
    and 100 x (1 - worst 32 x 32 tile)."""
    if colour:
        s, m = skmetrics.structural_similarity(a, b, channel_axis=2, data_range=255, gaussian_weights=True, full=True)
        m = m.mean(axis=2)
    else:
        ga, gb = skcolor.rgb2gray(a), skcolor.rgb2gray(b)
        s, m = skmetrics.structural_similarity(ga, gb, data_range=1.0, gaussian_weights=True, full=True)
    tiles = m.reshape(8, 32, 8, 32).mean(axis=(1, 3))
    return 100 * (1 - s), 100 * (1 - tiles.min())


def ms_ssim(a, b):
    """Multi-scale SSIM (Wang et al. weights) on 256 x 256 grey."""
    weights = [0.0448, 0.2856, 0.3001, 0.2363, 0.1333]
    x, y = skcolor.rgb2gray(a), skcolor.rgb2gray(b)
    vals = []
    for i, w in enumerate(weights):
        s = skmetrics.structural_similarity(x, y, data_range=1.0, gaussian_weights=True, win_size=7 if x.shape[0] >= 7 else 3)
        vals.append(max(s, 1e-6) ** w)
        if i < len(weights) - 1:
            x = x.reshape(x.shape[0] // 2, 2, x.shape[1] // 2, 2).mean(axis=(1, 3))
            y = y.reshape(y.shape[0] // 2, 2, y.shape[1] // 2, 2).mean(axis=(1, 3))
    return 100 * (1 - float(np.prod(vals)))


def gmsd(a, b):
    """Gradient magnitude similarity deviation (Xue et al.) on 256 grey."""
    x, y = skcolor.rgb2gray(a) * 255, skcolor.rgb2gray(b) * 255
    def grad(z):
        gx = (z[1:-1, 2:] - z[1:-1, :-2]) / 2
        gy = (z[2:, 1:-1] - z[:-2, 1:-1]) / 2
        return np.sqrt(gx * gx + gy * gy)
    gx, gy = grad(x), grad(y)
    c = 170.0
    gms = (2 * gx * gy + c) / (gx * gx + gy * gy + c)
    return float(gms.std() * 100)


def _conv_same(x, k):
    """MATLAB's conv2(x, k, 'same'), which centres an even-sized kernel
    differently from SciPy's (the HaarPSI reference code's helper)."""
    return np.rot90(signal.convolve2d(np.rot90(x, 2), np.rot90(k, 2), mode="same"), 2)


def haarpsi(a, b):
    """HaarPSI (Reisenhofer et al. 2018) on 256 x 256 colour, as the authors'
    reference code computes it: 100 x (1 - similarity)."""
    c, alpha, scales = 30.0, 4.2, 3
    mean2 = np.ones((2, 2)) / 4

    def yiq(x):
        r, g, bl = (x[..., k].astype(np.float64) for k in range(3))
        return [_conv_same(p, mean2)[::2, ::2] for p in (0.299 * r + 0.587 * g + 0.114 * bl,
                                                         0.596 * r - 0.274 * g - 0.322 * bl,
                                                         0.211 * r - 0.523 * g + 0.312 * bl)]

    def haar(y):
        out = ([], [])  # per orientation, per scale
        for s in range(1, scales + 1):
            k = 2.0 ** -s * np.ones((2 ** s, 2 ** s))
            k[:k.shape[0] // 2] *= -1
            out[0].append(_conv_same(y, k))
            out[1].append(_conv_same(y, k.T))
        return out

    def similar(x, y):
        return (2 * x * y + c) / (x * x + y * y + c)

    (ya, ia, qa), (yb, ib, qb) = yiq(a), yiq(b)
    ha, hb = haar(ya), haar(yb)
    sims, weights = [], []
    for o in range(2):
        weights.append(np.maximum(np.abs(ha[o][2]), np.abs(hb[o][2])))
        sims.append((similar(np.abs(ha[o][0]), np.abs(hb[o][0])) + similar(np.abs(ha[o][1]), np.abs(hb[o][1]))) / 2)
    sims.append((similar(np.abs(_conv_same(ia, mean2)), np.abs(_conv_same(ib, mean2)))
                 + similar(np.abs(_conv_same(qa, mean2)), np.abs(_conv_same(qb, mean2)))) / 2)
    weights.append((weights[0] + weights[1]) / 2)
    sims, weights = np.stack(sims), np.stack(weights)
    if weights.sum() == 0:
        return 0.0
    v = (weights / (1 + np.exp(-alpha * sims))).sum() / weights.sum()
    return float(100 * (1 - (np.log(v / (1 - v)) / alpha) ** 2))


def _vifp(ref, dist, sigma_nsq=2.0):
    """Pixel-domain VIF of dist against ref, as sewar and the authors'
    MATLAB code compute it (Gaussian windows, 'valid' filtering)."""
    eps = 1e-10
    num = den = 0.0
    x, y = ref, dist
    for scale in range(1, 5):
        n = 2 ** (4 - scale + 1) + 1
        g1 = np.exp(-((np.arange(n) - n // 2) ** 2) / (2 * (n / 5) ** 2))
        g1 /= g1.sum()

        def filt(z):
            z = signal.convolve(z, g1[:, None], mode="valid", method="direct")
            return signal.convolve(z, g1[None, :], mode="valid", method="direct")

        if scale > 1:
            x, y = filt(x)[::2, ::2], filt(y)[::2, ::2]
        mx, my = filt(x), filt(y)
        sxx = filt(x * x) - mx * mx
        syy = filt(y * y) - my * my
        sxy = filt(x * y) - mx * my
        sxx[sxx < 0] = 0
        syy[syy < 0] = 0
        g = sxy / (sxx + eps)
        sv = syy - g * sxy
        flat = sxx < eps
        g[flat] = 0
        sv[flat] = syy[flat]
        sxx[flat] = 0
        g[syy < eps] = 0
        sv[syy < eps] = 0
        neg = g < 0
        sv[neg] = syy[neg]
        g[neg] = 0
        sv[sv <= eps] = eps
        num += np.log10(1 + g * g * sxx / (sv + sigma_nsq)).sum()
        den += np.log10(1 + sxx / sigma_nsq).sum()
    return num / den if den > 0 else 1.0


def vifp(a, b):
    """Pixel-domain VIF (Sheikh and Bovik 2006) on 256 x 256 grey. VIF
    measures one image against a reference, and neither is the reference
    here: 100 x (1 - the smaller of both ways round)."""
    x, y = skcolor.rgb2gray(a) * 255, skcolor.rgb2gray(b) * 255
    return float(max(0.0, 100 * (1 - min(_vifp(x, y), _vifp(y, x)))))


def ciede2000(a, b):
    """CIEDE2000 colour difference on 128 x 128: mean and 99th percentile."""
    la = skcolor.rgb2lab(a[::2, ::2] / 255.0)
    lb = skcolor.rgb2lab(b[::2, ::2] / 255.0)
    d = skcolor.deltaE_ciede2000(la, lb)
    return float(d.mean()), float(np.percentile(d, 99))


def psnr(a, b):
    mse = ((a.astype(np.float64) - b.astype(np.float64)) ** 2).mean()
    return 0.0 if mse == 0 else 100.0 - 10 * np.log10(255 ** 2 / mse)  # 100 - PSNR: larger = more different


def hist_distance(ha, hb):
    """1 - histogram intersection, and the Bhattacharyya distance."""
    inter = 1 - np.minimum(ha, hb).sum()
    bc = np.sqrt(ha * hb).sum()
    return float(inter), float(np.sqrt(max(0.0, 1 - bc)))


def hamming(x, y):
    return int(np.count_nonzero(x != y))


def crop_resistant(ha, hb):
    """1 - share of the segments of the image with fewer segments that have a
    match (Hamming distance at most 10) in the other."""
    try:
        matches, _ = ha.hash_diff(hb, hamming_cutoff=10)
        return 1 - matches / max(1, min(len(ha.segment_hashes), len(hb.segment_hashes)))
    except Exception:
        return 1.0


def align(fa, fb):
    """SIFT matches (ratio test) and a RANSAC similarity transform from b's
    512 px copy to a's. Returns (inliers, matches, transform or None)."""
    ka, kb, da, db = fa["sift_keys"], fb["sift_keys"], fa["sift_desc"], fb["sift_desc"]
    if len(ka) < 8 or len(kb) < 8:
        return 0, 0, None
    m = skfeature.match_descriptors(db, da, max_ratio=0.8, cross_check=True)
    if len(m) < 8:
        return 0, len(m), None
    src, dst = kb[m[:, 0]][:, ::-1], ka[m[:, 1]][:, ::-1]  # (x, y)
    model, inliers = skmeasure.ransac((src, dst), sktransform.SimilarityTransform, min_samples=3,
                                      residual_threshold=2.0, max_trials=500, rng=0)
    if model is None or inliers is None:
        return 0, len(m), None
    return int(inliers.sum()), len(m), model


def cv_align(fa, fb, name):
    """ORB or AKAZE matches (ratio test) and a RANSAC similarity transform
    from b's 512 px copy to a's, like align(); None without OpenCV."""
    if fa.get(name) is None or fb.get(name) is None:
        return None
    (pa, da), (pb, db) = fa[name], fb[name]
    if da is None or db is None or len(pa) < 8 or len(pb) < 8:
        return 0, 0, None
    knn = cv2.BFMatcher(cv2.NORM_HAMMING).knnMatch(db, da, k=2)
    good = [m[0] for m in knn if len(m) == 2 and m[0].distance < 0.8 * m[1].distance]
    if len(good) < 8:
        return 0, len(good), None
    src = pb[[m.queryIdx for m in good]]
    dst = pa[[m.trainIdx for m in good]]
    matrix, mask = cv2.estimateAffinePartial2D(src, dst, method=cv2.RANSAC, ransacReprojThreshold=2.0,
                                               maxIters=2000, confidence=0.995)
    # A fit on collapsed points can come back with scale 0, which has no
    # inverse.
    if matrix is None or not np.isfinite(matrix).all() or np.hypot(matrix[0, 0], matrix[1, 0]) < 1e-3:
        return 0, len(good), None
    return int(mask.sum()), len(good), sktransform.SimilarityTransform(matrix=np.vstack([matrix, [0, 0, 1]]))


def cv_hash_distance(name, ha, hb):
    """OpenCV's own comparison of two img_hash hashes as a difference:
    Hamming distance (block mean, Marr-Hildreth), L2 (colour moments), and
    1 - the peak cross-correlation (radial variance)."""
    v = float(cv_hasher(name).compare(ha, hb))
    return 1 - v if name == "cv-radialvariance" else v


def clip_to_rect(poly, w, h):
    """The polygon clipped to the rectangle 0..w x 0..h (Sutherland-Hodgman)."""
    def clip(points, inside, cut):
        out = []
        for k in range(len(points)):
            p, q = points[k - 1], points[k]
            if inside(q):
                if not inside(p):
                    out.append(cut(p, q))
                out.append(q)
            elif inside(p):
                out.append(cut(p, q))
        return out

    def at_x(x):
        return lambda p, q: (x, p[1] + (q[1] - p[1]) * (x - p[0]) / (q[0] - p[0]))

    def at_y(y):
        return lambda p, q: (p[0] + (q[0] - p[0]) * (y - p[1]) / (q[1] - p[1]), y)

    pts = [tuple(p) for p in poly]
    for inside, cut in ((lambda p: p[0] >= 0, at_x(0)), (lambda p: p[0] <= w, at_x(w)),
                        (lambda p: p[1] >= 0, at_y(0)), (lambda p: p[1] <= h, at_y(h))):
        if not pts:
            break
        pts = clip(pts, inside, cut)
    return pts


def area(pts):
    if len(pts) < 3:
        return 0.0
    x = np.array([p[0] for p in pts])
    y = np.array([p[1] for p in pts])
    return float(abs(np.dot(x, np.roll(y, -1)) - np.dot(y, np.roll(x, -1))) / 2)


def overlap_shares(fa, fb, model):
    """Share of a covered by b's outline once aligned, and share of b
    covered by a's: (1, 1) for the same framing; (k, 1) when b is a crop of
    a keeping the share k of it."""
    ha, wa = fa["sift_shape"]
    hb, wb = fb["sift_shape"]
    poly_b_in_a = model(np.array([[0, 0], [wb, 0], [wb, hb], [0, hb]], dtype=np.float64))
    poly_a_in_b = model.inverse(np.array([[0, 0], [wa, 0], [wa, ha], [0, ha]], dtype=np.float64))
    share_a = area(clip_to_rect(poly_b_in_a, wa, ha)) / (wa * ha)
    share_b = area(clip_to_rect(poly_a_in_b, wb, hb)) / (wb * hb)
    return share_a, share_b


def libjxl_pair(tool, a_png, b_png, args=()):
    out = subprocess.run([os.path.join(LIBJXL, tool), a_png, b_png, *args], capture_output=True, text=True)
    return out.stdout + out.stderr


def butteraugli(a_png, b_png):
    """libjxl butteraugli_main: max-norm and 3-norm."""
    text = libjxl_pair("butteraugli_main.exe", a_png, b_png, ("--pnorm", "3"))
    nums = []
    for line in text.splitlines():
        for tok in line.replace(":", " ").split():
            try:
                nums.append(float(tok))
            except ValueError:
                pass
    return (nums[0], nums[-1]) if len(nums) >= 2 else (float("nan"), float("nan"))


def ssimulacra2(a_png, b_png):
    """libjxl ssimulacra2, turned into a difference: 100 - score."""
    text = libjxl_pair("ssimulacra2.exe", a_png, b_png)
    for tok in reversed(text.split()):
        try:
            return 100.0 - float(tok)
        except ValueError:
            pass
    return float("nan")


def detail(path):
    """RMS (0-255) of what halving and restoring the size removes from the
    grey image: the detail finer than half its resolution. An image blown
    up from a smaller one has little of it, whatever its pixel count."""
    g = open_image(path).convert("L")
    small = g.resize((max(1, g.width // 2), max(1, g.height // 2)), Image.BOX)
    back = np.asarray(small.resize(g.size, Image.BICUBIC), dtype=np.float64)
    d = np.asarray(g, dtype=np.float64) - back
    return float(np.sqrt((d * d).mean()))


def same_size_png(src_png, size, out_png):
    Image.open(src_png).convert("RGB").resize(size, Image.BOX).save(out_png)
