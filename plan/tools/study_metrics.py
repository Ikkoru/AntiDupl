"""Per-image features and pair metrics of the study (plan 07), used by
settings_study.py. Every metric is a difference: 0 for identical images,
larger for more different ones (similarities are turned around).

Image features (features(), cached by settings_study.py):
    planes      AntiDupl's reduced planes, grey and B/G/R, bilinear (its
                pipeline, bit-faithful via adsim) and area, sizes 16-128
    sq256       256 x 256 RGB, area-resampled, aspect ignored like AntiDupl
    hist        HSV histogram, 8 x 8 x 8, normalised
    hashes      aHash, dHash, pHash, wHash (64 bit), colorhash (from a
                512 px copy), crop-resistant hash
    sift        SIFT keypoints (row, col) and descriptors on a 512 px grey
                copy, for alignment
    quality     pixels, bytes per pixel, JPEG quality estimate (from the
                quantisation tables), Laplacian sharpness at native size
and two working copies for the libjxl tools (longest side 512 and 1024),
written by settings_study.py.
"""
import os
import subprocess

import imagehash
import numpy as np
from PIL import Image
from skimage import color as skcolor
from skimage import feature as skfeature
from skimage import measure as skmeasure
from skimage import metrics as skmetrics
from skimage import transform as sktransform

import adsim

Image.MAX_IMAGE_PIXELS = None
SIZES = [16, 32, 64, 128]
C1, C2 = (0.01 * 255) ** 2, (0.03 * 255) ** 2
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
    hashes = {"ahash": imagehash.average_hash(small).hash.flatten(), "dhash": imagehash.dhash(small).hash.flatten(),
              "phash": imagehash.phash(small).hash.flatten(), "whash": imagehash.whash(small).hash.flatten(),
              "colorhash": imagehash.colorhash(small).hash.flatten()}
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
    return {
        "planes": planes, "sq256": sq256, "hist": hist, "hashes": hashes, "crh": crh,
        "sift_keys": keys, "sift_desc": desc, "sift_shape": g512.shape,
        "pixels": rgb.shape[0] * rgb.shape[1], "shape": rgb.shape[:2],
        "bpp": os.path.getsize(path) / (rgb.shape[0] * rgb.shape[1]),
        "jpeg_quality": quality, "sharpness": float(lap.var()),
    }


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


def same_size_png(src_png, size, out_png):
    Image.open(src_png).convert("RGB").resize(size, Image.BOX).save(out_png)
