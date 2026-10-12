"""Settings study (plan 07): every algorithm and setting on every pair of a
sample set, judged on three tasks.

Usage: py -3 settings_study.py <set> <cache> <out> [--dll <bin\\Release>]
                                [--workers N] [--no-slow]

<set> is study_set.py's output (one folder per case, each with
manifest.tsv). <cache> holds per-image features and working copies
(rebuildable, gets a CACHEDIR.TAG). --dll: a build whose AntiDupl.dll
gives the core's blockiness and blurring per image (via core_search.py).
--no-slow leaves out Butteraugli and SSIMULACRA2.

Writes to <out>: pairs.csv (one row per pair, a column per metric),
quality.csv (per image), summary.md (the tables of plan 07).

Pairs: every pair within a case, and each case's original against every
image of the other cases ("unrelated"). Classes (clean = the original or a
copy of it):
    copy            clean~clean: to be found, the worse one deleted
    versions        clean~variant, variant~variant, clean~step, clean~edit:
                    to be kept apart, in classes variant-minor/-medium/-major
                    (under 1 %, 1-5 %, 5 % or more of the picture changed),
                    sketch/wip-far/wip-close (first quarter, middle, last
                    quarter of the steps), edit-minor (sign, bar), edit-medium
                    (mosaic, smudge, clone, local recolour), edit-major
                    (global recolour)
    crop, overlay, gray, transform
                    clean~those: whether they are copies is the user's call
    other, unrelated
Tasks:
    A  copies vs versions: per metric, with the results sorted by it, how
       many versions come before the last copy, overall and per copy type
    B  which copy is worse: pairs of copies/crops that differ in one way
       (compression, resolution, crop) or are a web copy of the original;
       per quality indicator, how often it picks the worse one
    C  is one a crop or transform of the other: SIFT alignment, against the
       truth of the manifests
"""
import argparse
import csv
import itertools
import os
import pickle
import subprocess
import sys
import tempfile
from concurrent.futures import ProcessPoolExecutor

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import study_metrics as sm  # noqa: E402

TAG = "Signature: 8a477f597d28d172789f06886806bc55\n# Settings study feature cache: rebuilt by plan/tools/settings_study.py\n"
VERSION_CLASSES = ["variant-minor", "variant-medium", "variant-major", "sketch", "wip-far", "wip-close",
                   "edit-minor", "edit-medium", "edit-major"]
EDIT_CLASS = {"sign": "edit-minor", "bar": "edit-minor", "mosaic": "edit-medium", "smudge": "edit-medium",
              "clone": "edit-medium", "recolour-local": "edit-medium", "recolour-global": "edit-major"}
CLEAN = {"original", "copy"}
VERSIONS = {"variant", "step", "edit"}


# ----------------------------------------------------------------- images

def load_set(set_dir):
    images = []
    for case in sorted(os.listdir(set_dir)):
        manifest = os.path.join(set_dir, case, "manifest.tsv")
        if not os.path.isfile(manifest):
            continue
        for r in csv.DictReader(open(manifest, encoding="utf-8"), delimiter="\t"):
            r["case"] = case
            r["path"] = os.path.join(set_dir, case, r["file"])
            r["stem"] = r["file"].rsplit(".", 1)[0]
            images.append(r)
    return images


def cache_paths(cache, img):
    base = os.path.join(cache, img["case"], img["stem"])
    return base + ".pkl", base + "-512.png", base + "-1024.png"


def build_features(job):
    path, pkl, w512, w1024 = job
    stamp = (os.path.getsize(path), os.path.getmtime(path))
    if os.path.exists(pkl):
        try:
            with open(pkl, "rb") as f:
                if pickle.load(f)["stamp"] == stamp and os.path.exists(w512) and os.path.exists(w1024):
                    return pkl
        except Exception:
            pass
    os.makedirs(os.path.dirname(pkl), exist_ok=True)
    feats = sm.features(path)
    feats["stamp"] = stamp
    im = sm.open_image(path).convert("RGB")
    sm.longest(im, 512).save(w512)
    sm.longest(im, 1024).save(w1024)
    feats["rgb512"] = np.asarray(Image.open(w512))
    with open(pkl, "wb") as f:
        pickle.dump(feats, f, protocol=5)
    return pkl


# ------------------------------------------------------------------ pairs

def changed_area(fa, fb):
    a, b = fa["rgb512"], fb["rgb512"]
    if a.shape != b.shape or fa["shape"] != fb["shape"]:
        return None
    return float((np.abs(a.astype(np.int16) - b.astype(np.int16)).max(axis=2) > 24).mean())


def variant_class(changed):
    return "variant-minor" if changed < 0.01 else "variant-medium" if changed < 0.05 else "variant-major"


def step_class(detail):
    i, n = (int(x) for x in detail.replace("step ", "").split(" of "))
    return "sketch" if i <= n / 4 else "wip-close" if i > n * 3 / 4 else "wip-far"


def pair_class(a, b, changed, original_changed):
    if a["case"] != b["case"]:
        return "unrelated"
    ka, kb = a["kind"], b["kind"]
    if ka in CLEAN and kb in CLEAN:
        return "copy"
    if ka == "variant" and kb == "variant":
        return variant_class(changed) if changed is not None else "other"
    c, v = (a, b) if ka in CLEAN else (b, a)
    if c["kind"] not in CLEAN:
        return "other"
    if v["kind"] == "variant":
        oc = original_changed.get((v["case"], v["file"]))
        return variant_class(oc) if oc is not None else "other"
    if v["kind"] == "step":
        return step_class(v["detail"])
    if v["kind"] == "edit":
        return EDIT_CLASS[v["stem"]]
    return v["kind"]  # crop, overlay, gray, transform


_feats = {}


def feats(pkl):
    # Pairs come in order of their first image, so a small cache per
    # worker serves most of them.
    if pkl not in _feats:
        if len(_feats) > 40:
            _feats.clear()
        with open(pkl, "rb") as f:
            _feats[pkl] = pickle.load(f)
    return _feats[pkl]


def metric_names(slow):
    names = []
    for alg in ("ssim", "msd"):
        for colour in ("gray", "colour"):
            for resample in ("bilinear", "area"):
                for s in sm.SIZES:
                    names.append(f"antidupl-{alg}-{colour}-{resample}-{s}")
    names += [f"colour-block-{s}" for s in (32, 64, 128)]
    names += ["wssim-gray-mean", "wssim-gray-worst", "wssim-colour-mean", "wssim-colour-worst", "ms-ssim", "gmsd",
              "ciede2000-mean", "ciede2000-p99", "psnr", "hist-intersection", "hist-bhattacharyya",
              "ahash", "dhash", "phash", "whash", "colorhash", "crop-resistant-hash",
              "sift-unmatched", "aligned-colour-block-64"]
    if slow:
        names += ["butteraugli-512", "butteraugli-3norm-512", "butteraugli-1024", "butteraugli-3norm-1024",
                  "ssimulacra2-512", "ssimulacra2-1024"]
    return names


def aligned_block(fa, fb, model):
    """Colour block difference (64 px grid of 4 x 4 blocks) between a and b
    warped onto a with the SIFT transform, over the blocks both cover; None
    without a transform."""
    from skimage import transform as sktransform
    a = fa["rgb512"].astype(np.float64)
    b = fb["rgb512"].astype(np.float64)
    warped = sktransform.warp(b, model.inverse, output_shape=a.shape[:2], order=1, preserve_range=True, cval=-1)
    valid = (warped[..., 0] >= 0).astype(np.float64)
    warped = np.where(warped < 0, 0, warped)
    def grid(x):
        im = Image.fromarray(np.clip(x, 0, 255).astype(np.uint8) if x.ndim == 3 else (x * 255).astype(np.uint8))
        return np.asarray(im.resize((64, 64), Image.BOX), dtype=np.float64)
    ga, gb, gv = grid(a), grid(warped), grid(valid) / 255
    d2 = ((ga - gb) ** 2).mean(axis=2)
    blocks = d2.reshape(16, 4, 16, 4).mean(axis=(1, 3))
    cover = gv.reshape(16, 4, 16, 4).min(axis=(1, 3))
    usable = blocks[cover > 0.99]
    if usable.size < 16:
        return None
    return float(np.sqrt(usable.max()) / 255 * 100)


def compute_pairs(job):
    pairs, slow, tmp = job
    out = []
    for (ia, pa, wa512, wa1024, ib, pb, wb512, wb1024) in pairs:
        fa, fb = feats(pa), feats(pb)
        row = {"a": ia, "b": ib}
        for alg in ("ssim", "msd"):
            for colour in ("gray", "colour"):
                for resample in ("bilinear", "area"):
                    for s in sm.SIZES:
                        x, y = fa["planes"][(colour, resample, s)], fb["planes"][(colour, resample, s)]
                        row[f"antidupl-{alg}-{colour}-{resample}-{s}"] = sm.antidupl_ssim(x, y) if alg == "ssim" else sm.antidupl_msd(x, y)
        for s in (32, 64, 128):
            row[f"colour-block-{s}"] = sm.colour_block(fa["planes"][("colour", "area", s)], fb["planes"][("colour", "area", s)])
        qa, qb = fa["sq256"], fb["sq256"]
        row["wssim-gray-mean"], row["wssim-gray-worst"] = sm.windowed_ssim(qa, qb, False)
        row["wssim-colour-mean"], row["wssim-colour-worst"] = sm.windowed_ssim(qa, qb, True)
        row["ms-ssim"] = sm.ms_ssim(qa, qb)
        row["gmsd"] = sm.gmsd(qa, qb)
        row["ciede2000-mean"], row["ciede2000-p99"] = sm.ciede2000(qa, qb)
        row["psnr"] = sm.psnr(qa, qb)
        row["hist-intersection"], row["hist-bhattacharyya"] = sm.hist_distance(fa["hist"], fb["hist"])
        for h in ("ahash", "dhash", "phash", "whash", "colorhash"):
            row[h] = sm.hamming(fa["hashes"][h], fb["hashes"][h])
        row["crop-resistant-hash"] = sm.crop_resistant(fa["crh"], fb["crh"])
        inliers, matches, model = sm.align(fa, fb)
        row["sift-inliers"], row["sift-matches"] = inliers, matches
        smaller = max(1, min(len(fa["sift_keys"]), len(fb["sift_keys"])))
        row["sift-unmatched"] = 1 - inliers / smaller
        if model is not None and inliers >= 15:
            share_a, share_b = sm.overlap_shares(fa, fb, model)
            row["share-a"], row["share-b"] = share_a, share_b
            row["align-scale"], row["align-rotation"] = float(model.scale), float(np.degrees(model.rotation))
            ab = aligned_block(fa, fb, model)
            row["aligned-colour-block-64"] = ab if ab is not None else row["colour-block-64"]
        else:
            row["share-a"] = row["share-b"] = row["align-scale"] = row["align-rotation"] = ""
            row["aligned-colour-block-64"] = row["colour-block-64"]
        if slow:
            for side, wa, wb in ((512, wa512, wb512), (1024, wa1024, wb1024)):
                size = Image.open(wa).size
                b_png = os.path.join(tmp, f"b-{os.getpid()}-{side}.png")
                sm.same_size_png(wb, size, b_png)
                row[f"butteraugli-{side}"], row[f"butteraugli-3norm-{side}"] = sm.butteraugli(wa, b_png)
                row[f"ssimulacra2-{side}"] = sm.ssimulacra2(wa, b_png)
        out.append(row)
    return out


# ------------------------------------------------------------- core values

def core_values(dll, set_dir, cases, tmp):
    """The core's blockiness and blurring per image path (images in no pair
    under the largest SSIM threshold are missing)."""
    values = {}
    for case in cases:
        tsv = os.path.join(tmp, f"core-{case}.tsv")
        subprocess.run([sys.executable, os.path.join(HERE, "core_search.py"), dll, os.path.join(tmp, "core-user"),
                        os.path.join(set_dir, case), "--size", "128", "--threshold", "50", "--images", tsv],
                       check=True, capture_output=True)
        for r in csv.DictReader(open(tsv, encoding="utf-8"), delimiter="\t"):
            values[os.path.normcase(os.path.abspath(r["path"]))] = (float(r["blockiness"]), float(r["blurring"]))
    return values


# --------------------------------------------------------------- analysis

def auc(copies, versions):
    """Probability that a copy pair has a smaller value than a version pair
    (ties half): 1 = perfect order, 0.5 = chance."""
    c, v = np.sort(np.asarray(copies)), np.asarray(versions)
    less = np.searchsorted(c, v, side="left")
    equal = np.searchsorted(c, v, side="right") - less
    return float((less + equal / 2).sum() / (len(c) * len(v)))


def task_a(rows, names, images, lines):
    lines += ["## A. Copies vs versions", "",
              "Results sorted by the metric, smallest first, as the user works through them. **Before last copy**: "
              "how many version pairs (of all) come before the last copy pair. **AUC**: the chance that a copy pair "
              "comes before a version pair (1 = always). Per copy type below: how many versions come before the "
              "original~that-copy pairs.", ""]
    versions_all = [r for r in rows if r["class"] in VERSION_CLASSES]
    copies = [r for r in rows if r["class"] == "copy"]
    lines += [f"{len(copies)} copy pairs, {len(versions_all)} version pairs.", "",
              "| Metric | AUC | Before last copy | Before last copy, without the 12-25 % copies |", "|---|---|---|---|"]
    table = []
    small = ("scale-12", "scale-25", "scale-25-jpeg-q75")
    for n in names:
        cv = [r[n] for r in copies if r[n] != ""]
        vv = [r[n] for r in versions_all if r[n] != ""]
        cmax = max(cv)
        before = sum(1 for x in vv if x <= cmax)
        cv2 = [r[n] for r in copies if r[n] != "" and not any(s == images[r["a"]]["stem"] or s == images[r["b"]]["stem"] for s in small)]
        before2 = sum(1 for x in vv if x <= max(cv2))
        table.append((auc(cv, vv), n, before, before2, len(vv)))
    table.sort(key=lambda t: (-t[0], t[2]))
    for a_, n, before, before2, total in table:
        lines.append(f"| {n} | {a_:.4f} | {before} ({100 * before / total:.1f} %) | {before2} ({100 * before2 / total:.1f} %) |")
    # Per copy type and per class, for every metric.
    copy_types = sorted({images[r["b"]]["stem"] if images[r["a"]]["kind"] == "original" else images[r["a"]]["stem"]
                         for r in copies if "original" in (images[r["a"]]["kind"], images[r["b"]]["kind"])})
    lines += ["", "### Versions before each copy type", "",
              "Versions with a value at or below the largest value of original~<copy type> over the cases.", "",
              "| Metric | " + " | ".join(copy_types) + " |", "|---|" + "---|" * len(copy_types)]
    for n in names:
        vv = np.array([r[n] for r in versions_all if r[n] != ""])
        cells = []
        for t in copy_types:
            tv = [r[n] for r in copies if r[n] != "" and "original" in (images[r["a"]]["kind"], images[r["b"]]["kind"])
                  and t in (images[r["a"]]["stem"], images[r["b"]]["stem"])]
            cells.append(str(int((vv <= max(tv)).sum())) if tv else "-")
        lines.append(f"| {n} | " + " | ".join(cells) + " |")
    lines += ["", "### Version classes before the last copy (without the 12-25 % copies)", "",
              "| Metric | " + " | ".join(VERSION_CLASSES) + " |", "|---|" + "---|" * len(VERSION_CLASSES)]
    for n in names:
        cv2 = [r[n] for r in copies if r[n] != "" and not any(s in (images[r["a"]]["stem"], images[r["b"]]["stem"]) for s in small)]
        t = max(cv2)
        cells = []
        for c in VERSION_CLASSES:
            vals = [r[n] for r in rows if r["class"] == c and r[n] != ""]
            cells.append(f"{sum(1 for x in vals if x <= t)}/{len(vals)}")
        lines.append(f"| {n} | " + " | ".join(cells) + " |")
    lines += ["", "### The user's calls: where crops, overlays, greyscale and transforms land", "",
              "Per derived kind: the share of version pairs with a smaller value than the median of original~that "
              "kind (0 % = it sorts among the copies, 100 % = after every version).", ""]
    kinds = sorted({images[r["b"]]["stem"] if images[r["a"]]["kind"] == "original" else images[r["a"]]["stem"]
                    for r in rows if r["class"] in ("crop", "overlay", "gray", "transform")
                    and "original" in (images[r["a"]]["kind"], images[r["b"]]["kind"])})
    lines += ["| Metric | " + " | ".join(kinds) + " |", "|---|" + "---|" * len(kinds)]
    for n in names:
        vv = np.array([r[n] for r in versions_all if r[n] != ""])
        cells = []
        for k in kinds:
            kv = [r[n] for r in rows if r[n] != "" and "original" in (images[r["a"]]["kind"], images[r["b"]]["kind"])
                  and k in (images[r["a"]]["stem"], images[r["b"]]["stem"]) and r["class"] in ("crop", "overlay", "gray", "transform")]
            cells.append(f"{100 * (vv < np.median(kv)).mean():.0f} %" if kv else "-")
        lines.append(f"| {n} | " + " | ".join(cells) + " |")


def loss(img):
    """(scale, quality, generations, kept, codec) of a clean or cropped
    image; the original is lossless at full size."""
    if img["kind"] == "original":
        return 1.0, 100.0, 0, 1.0, "lossless"
    ext = img["file"].rsplit(".", 1)[1].lower()
    codec = {"jpg": "jpeg", "jpeg": "jpeg", "webp": "webp", "avif": "avif", "jxl": "jxl"}.get(ext, "lossless")
    q = img["quality"]
    quality = 100.0 if codec == "lossless" else float(q) if q.replace(".", "").isdigit() else None
    return float(img["scale"]), quality, int(img["generations"]), float(img["kept"]), codec


def task_b(images, quality, lines):
    lines += ["", "## B. Which copy is worse", "",
              "Pairs of the same picture (original, copies, crops of one case) that differ in one way, so one is "
              "known to be worse: **compression** (same size, one more lossy: a lower quality of the same codec, "
              "more re-encodings, or lossy against the original), **resolution** (lossless, one smaller), **crop** "
              "(lossless, full size, one shows less), **web copy** (the original against a copy that is smaller and "
              "compressed). Per indicator: the share of pairs where it ranks the worse one lower (ties count half); "
              "\"-\" where it has no value for those images.", ""]
    groups = {"compression": [], "resolution": [], "crop": [], "web copy": []}
    for case in sorted({i["case"] for i in images}):
        pool = [i for i, img in enumerate(images) if img["case"] == case and img["kind"] in ("original", "copy", "crop")]
        for i, j in itertools.combinations(pool, 2):
            (sa, qa, ga, ka, ca), (sb, qb, gb, kb, cb) = loss(images[i]), loss(images[j])
            if None in (qa, qb):
                continue
            better = None
            if sa == sb == 1 and ka == kb == 1 and "upscale" not in images[i]["stem"] + images[j]["stem"]:
                if ca == cb and ca != "lossless" and (qa, -ga) != (qb, -gb) and (qa >= qb) == (-ga >= -gb):
                    better, kind = (i if (qa, -ga) > (qb, -gb) else j), "compression"
                elif {ca, cb} & {"lossless"} and ca != cb and images[i if ca == "lossless" else j]["kind"] == "original":
                    better, kind = (i if ca == "lossless" else j), "compression"
            elif ca == cb == "lossless" and ka == kb == 1 and sa != sb and "bilinear" not in images[i]["stem"] + images[j]["stem"] \
                    and "nearest" not in images[i]["stem"] + images[j]["stem"] and "upscale" not in images[i]["stem"] + images[j]["stem"]:
                better, kind = (i if sa > sb else j), "resolution"
            elif ca == cb == "lossless" and sa == sb == 1 and ka != kb and "rescaled" not in images[i]["stem"] + images[j]["stem"]:
                better, kind = (i if ka > kb else j), "crop"
            elif images[i]["kind"] == "original" or images[j]["kind"] == "original":
                o, c = (i, j) if images[i]["kind"] == "original" else (j, i)
                s, q, g, k, cc = loss(images[c])
                if s < 1 and cc != "lossless" and k == 1:
                    better, kind = o, "web copy"
            if better is not None:
                groups[kind].append((better, j if better == i else i))
    indicators = [("pixels", lambda v: v["pixels"], 1), ("file size", lambda v: v["size"], 1),
                  ("bytes per pixel", lambda v: v["bpp"], 1), ("JPEG quality estimate", lambda v: v["jpeg_quality"], 1),
                  ("sharpness (Laplacian variance)", lambda v: v["sharpness"], 1),
                  ("AntiDupl blockiness", lambda v: v["blockiness"], -1), ("AntiDupl blurring", lambda v: v["blurring"], -1)]
    lines += ["| Indicator | " + " | ".join(f"{k} ({len(v)} pairs)" for k, v in groups.items()) + " |",
              "|---|" + "---|" * len(groups)]
    for name, get, sign in indicators:
        cells = []
        for k, pairs in groups.items():
            score, n = 0.0, 0
            for good, bad in pairs:
                x, y = get(quality[good]), get(quality[bad])
                if x is None or y is None or (isinstance(x, float) and np.isnan(x)) or (isinstance(y, float) and np.isnan(y)):
                    continue
                n += 1
                score += 1.0 if sign * x > sign * y else 0.5 if x == y else 0.0
            cells.append(f"{100 * score / n:.0f} % ({n})" if n else "-")
        lines.append(f"| {name} | " + " | ".join(cells) + " |")


def task_c(rows, images, lines):
    lines += ["", "## C. Crops and transforms", "",
              "SIFT keypoints on 512 px copies, matched and aligned with a similarity transform (RANSAC). A pair "
              "counts as **one a crop of the other** when at least 15 matches agree, the smaller one lies within the "
              "other (95 % of it covered) and covers under 97 % of the other. **Kept** compares the estimated share "
              "of the original still in the crop with the truth.", ""]
    def crop_of(r):
        if r["share-a"] == "" or r["sift-inliers"] < 15:
            return False
        a, b = r["share-a"], r["share-b"]
        return (b >= 0.95 and a < 0.97) or (a >= 0.95 and b < 0.97)
    groups = {}
    for r in rows:
        ia, ib = images[r["a"]], images[r["b"]]
        if r["class"] == "crop" and "original" in (ia["kind"], ib["kind"]):
            key = "original~crop"
        elif r["class"] == "copy":
            key = "copy pairs"
        elif r["class"] in VERSION_CLASSES:
            key = "version pairs"
        elif r["class"] == "unrelated":
            key = "unrelated"
        elif r["class"] == "transform" and "original" in (ia["kind"], ib["kind"]):
            key = "original~" + (ia["stem"] if ia["kind"] != "original" else ib["stem"])
        else:
            continue
        groups.setdefault(key, []).append(r)
    lines += ["| Pairs | Count | Aligned (15+ matches) | Judged a crop |", "|---|---|---|---|"]
    for key in ("original~crop", "copy pairs", "version pairs", "unrelated", "original~mirror", "original~rotate-90"):
        g = groups.get(key, [])
        if not g:
            continue
        aligned = sum(1 for r in g if r["sift-inliers"] >= 15)
        crops = sum(1 for r in g if crop_of(r))
        lines.append(f"| {key} | {len(g)} | {aligned} ({100 * aligned / len(g):.0f} %) | {crops} ({100 * crops / len(g):.0f} %) |")
    lines += ["", "| Crop | Kept (truth) | Kept (estimated, per case) | Rotation found |", "|---|---|---|---|"]
    for stem in ("crop-1", "crop-2", "crop-5", "crop-10", "crop-20", "crop-right-10", "crop-square", "crop-5-rescaled", "rotate-90", "mirror"):
        g = [r for r in rows if "original" in (images[r["a"]]["kind"], images[r["b"]]["kind"])
             and stem in (images[r["a"]]["stem"], images[r["b"]]["stem"]) and images[r["a"]]["case"] == images[r["b"]]["case"]]
        if not g:
            continue
        truth = images[g[0]["a"]]["kept"] if images[g[0]["a"]]["stem"] == stem else images[g[0]["b"]]["kept"]
        est = []
        rot = []
        for r in g:
            if r["share-a"] == "" or r["sift-inliers"] < 15:
                est.append("-")
                continue
            orig_is_a = images[r["a"]]["kind"] == "original"
            est.append(f"{(r['share-a'] if orig_is_a else r['share-b']):.2f}")
            rot.append(f"{r['align-rotation']:.0f}")
        lines.append(f"| {stem} | {truth} | {' '.join(est)} | {' '.join(rot) or '-'} |")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("set")
    ap.add_argument("cache")
    ap.add_argument("out")
    ap.add_argument("--dll")
    ap.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 2) - 2))
    ap.add_argument("--no-slow", action="store_true")
    ap.add_argument("--cases", help="comma-separated case names (default: all)")
    a = ap.parse_args()
    os.makedirs(a.cache, exist_ok=True)
    os.makedirs(a.out, exist_ok=True)
    with open(os.path.join(a.cache, "CACHEDIR.TAG"), "w", encoding="ascii", newline="\n") as f:
        f.write(TAG)
    images = load_set(a.set)
    if a.cases:
        images = [img for img in images if img["case"] in a.cases.split(",")]
    jobs = [(img["path"], *cache_paths(a.cache, img)) for img in images]
    with ProcessPoolExecutor(a.workers) as pool:
        list(pool.map(build_features, jobs, chunksize=1))
    print(f"{len(images)} images: features ready", flush=True)

    # Only what is small is kept here: the changed areas and the per-image
    # quality values.
    small, original_changed, changed_of = {}, {}, {}
    for i in range(len(images)):
        f = feats(jobs[i][1])
        small[i] = {"rgb512": f["rgb512"], "shape": f["shape"], "pixels": f["pixels"], "bpp": f["bpp"],
                    "jpeg_quality": f["jpeg_quality"], "sharpness": f["sharpness"]}
    _feats.clear()
    for i, img in enumerate(images):
        if img["kind"] == "variant":
            o = next(j for j, q in enumerate(images) if q["case"] == img["case"] and q["kind"] == "original")
            original_changed[(img["case"], img["file"])] = changed_area(small[o], small[i])
    pairs, classes = [], {}
    for i, j in itertools.combinations(range(len(images)), 2):
        same = images[i]["case"] == images[j]["case"]
        if not same and images[i]["kind"] != "original" and images[j]["kind"] != "original":
            continue
        changed = changed_area(small[i], small[j]) if same else None
        classes[(i, j)] = (pair_class(images[i], images[j], changed, original_changed), changed)
        pairs.append((i, jobs[i][1], jobs[i][2], jobs[i][3], j, jobs[j][1], jobs[j][2], jobs[j][3]))
    for i in small:
        del small[i]["rgb512"]
    print(f"{len(pairs)} pairs", flush=True)
    tmp = tempfile.mkdtemp(prefix="study-", dir=a.cache)
    chunks = [pairs[k:k + 40] for k in range(0, len(pairs), 40)]
    rows = []
    with ProcessPoolExecutor(a.workers) as pool:
        for n, part in enumerate(pool.map(compute_pairs, [(c, not a.no_slow, tmp) for c in chunks]), 1):
            rows.extend(part)
            if n % 20 == 0:
                print(f"  {n * 40} pairs done", flush=True)
    for r in rows:
        r["class"], changed = classes[(r["a"], r["b"])]
        r["changed"] = "" if changed is None else round(changed, 4)

    quality = {}
    core = core_values(a.dll, a.set, sorted({img["case"] for img in images}), tmp) if a.dll else {}
    for i, img in enumerate(images):
        f = small[i]
        bl = core.get(os.path.normcase(os.path.abspath(img["path"])), (None, None))
        quality[i] = {"pixels": f["pixels"], "size": os.path.getsize(img["path"]), "bpp": f["bpp"],
                      "jpeg_quality": f["jpeg_quality"], "sharpness": f["sharpness"],
                      "blockiness": bl[0], "blurring": bl[1]}
    with open(os.path.join(a.out, "quality.csv"), "w", encoding="utf-8", newline="") as fq:
        w = csv.writer(fq)
        w.writerow(["case", "file", "kind", "pixels", "size", "bpp", "jpeg_quality", "sharpness", "blockiness", "blurring"])
        for i, img in enumerate(images):
            q = quality[i]
            w.writerow([img["case"], img["file"], img["kind"], q["pixels"], q["size"], q["bpp"], q["jpeg_quality"],
                        q["sharpness"], q["blockiness"], q["blurring"]])

    names = metric_names(not a.no_slow)
    fields = ["case_a", "a", "case_b", "b", "class", "changed"] + names + \
             ["sift-inliers", "sift-matches", "share-a", "share-b", "align-scale", "align-rotation"]
    with open(os.path.join(a.out, "pairs.csv"), "w", encoding="utf-8", newline="") as fp:
        w = csv.DictWriter(fp, fields, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            out = dict(r)
            out["case_a"], out["case_b"] = images[r["a"]]["case"], images[r["b"]]["case"]
            out["a"], out["b"] = images[r["a"]]["file"], images[r["b"]]["file"]
            w.writerow(out)
    lines = ["# Settings study summary", "", f"Generated by `settings_study.py`: {len(images)} images in "
             f"{len({i['case'] for i in images})} cases, {len(rows)} pairs.", ""]
    task_a(rows, names, images, lines)
    task_b(images, quality, lines)
    task_c(rows, images, lines)
    with open(os.path.join(a.out, "summary.md"), "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(lines) + "\n")
    print("summary written", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
