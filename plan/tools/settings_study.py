"""Settings study (plan 07): every algorithm and setting on every pair of a
sample set, judged on three tasks.

Usage: py -3 settings_study.py <set> <cache> <out> [--dll <bin\\Release>]
                                [--workers N] [--no-slow] [--cases a,b]
                                [--analysis-only]

<set> is study_set.py's output (one folder per case, each with
manifest.tsv). <cache> holds per-image features and working copies
(rebuildable, gets a CACHEDIR.TAG). --dll: a build whose AntiDupl.dll
gives the core's blockiness and blurring per image (via core_search.py).
--no-slow leaves out Butteraugli and SSIMULACRA2. --analysis-only
rewrites summary.md from the pairs.csv and quality.csv already in <out>.

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
       many versions come before the last copy, overall, per kind of
       difference (compression, resolution, crop, ...) and per copy type
    B  which copy is worse: pairs of copies/crops that differ in one way
       (compression, resolution, crop, upscaling) or are a web copy of the
       original; per quality indicator, how often it picks the worse one
    C  is one a crop or transform of the other: SIFT alignment, against the
       truth of the manifests
"""
import argparse
import csv
import itertools
import os
import pickle
import shutil
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
# Kinds of difference of the derived images, by file stem.
GROUPS = [("compression", lambda s: s.startswith(("jpeg-", "webp-", "avif-", "jxl-"))),
          ("resolution", lambda s: s.startswith("scale-") and "jpeg" not in s),
          ("web copy", lambda s: s.startswith("scale-") and "jpeg" in s),
          ("upscaled", lambda s: s.startswith("upscale-")),
          ("processed", lambda s: s in ("sharpen", "blur", "brighter", "saturated")),
          ("crop", lambda s: s.startswith("crop-")),
          ("overlay", lambda s: s.startswith(("border-", "watermark-"))),
          ("greyscale", lambda s: s == "gray"),
          ("transform", lambda s: s in ("mirror", "rotate-90"))]
# Copies that differ from the original only in encoding and resolution.
PLAIN = {"original", "compression", "resolution", "web copy", "upscaled"}


def kind_of(img):
    """"original", the kind of difference of a derived image, or None."""
    if img["kind"] == "original":
        return "original"
    return next((g for g, test in GROUPS if test(img["stem"])), None)


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
                cached = pickle.load(f)
            if cached["stamp"] == stamp and os.path.exists(w512) and os.path.exists(w1024):
                if sm.needs_late(cached):
                    # Cached before some features were added: only those.
                    cached.update(sm.late_features(sm.longest(sm.open_image(path).convert("RGB"), 512)))
                    with open(pkl, "wb") as f:
                        pickle.dump(cached, f, protocol=5)
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
              "haarpsi", "vifp", "ciede2000-mean", "ciede2000-p99", "psnr", "hist-intersection", "hist-bhattacharyya",
              *sm.HASHES, "crop-resistant-hash", "sift-unmatched", "aligned-colour-block-64",
              *sm.CV_HASHES, "orb-unmatched", "orb-aligned-colour-block-64", "akaze-unmatched",
              "akaze-aligned-colour-block-64"]
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
        row["haarpsi"] = sm.haarpsi(qa, qb)
        row["vifp"] = sm.vifp(qa, qb)
        row["ciede2000-mean"], row["ciede2000-p99"] = sm.ciede2000(qa, qb)
        row["psnr"] = sm.psnr(qa, qb)
        row["hist-intersection"], row["hist-bhattacharyya"] = sm.hist_distance(fa["hist"], fb["hist"])
        for h in sm.HASHES:
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
        for name in sm.CV_HASHES:
            row[name] = "" if fa["cvhash"] is None or fb["cvhash"] is None else \
                sm.cv_hash_distance(name, fa["cvhash"][name], fb["cvhash"][name])
        for name in ("orb", "akaze"):
            found = sm.cv_align(fa, fb, name)
            if found is None:
                for k in ("unmatched", "aligned-colour-block-64", "inliers", "share-a", "share-b"):
                    row[f"{name}-{k}"] = ""
                continue
            inliers, matches, model = found
            row[f"{name}-inliers"] = inliers
            row[f"{name}-unmatched"] = 1 - inliers / max(1, min(len(fa[name][0]), len(fb[name][0])))
            row[f"{name}-share-a"] = row[f"{name}-share-b"] = ""
            row[f"{name}-aligned-colour-block-64"] = row["colour-block-64"]
            if model is not None and inliers >= 15:
                row[f"{name}-share-a"], row[f"{name}-share-b"] = sm.overlap_shares(fa, fb, model)
                ab = aligned_block(fa, fb, model)
                if ab is not None:
                    row[f"{name}-aligned-colour-block-64"] = ab
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
              "how many version pairs (of all) come before the last copy pair. **Plain copies**: the original and "
              "its compressed, resized, web and upscaled copies, any two of them; the processed copies (sharpened, "
              "blurred, brighter, more saturated) count only in the last column. **AUC**: the chance that a copy "
              "pair (any) comes before a version pair (1 = always). Per copy type below: how many versions come "
              "before the original~that-copy pairs.", ""]
    versions_all = [r for r in rows if r["class"] in VERSION_CLASSES]
    copies = [r for r in rows if r["class"] == "copy"]
    small = ("scale-12", "scale-25", "scale-25-jpeg-q75")
    plain = [r for r in copies if all(kind_of(images[r[k]]) in PLAIN for k in ("a", "b"))]
    plain_big = [r for r in plain if not any(images[r[k]]["stem"] in small for k in ("a", "b"))]
    lines += [f"{len(copies)} copy pairs ({len(plain)} plain), {len(versions_all)} version pairs.", "",
              "| Metric | AUC | Before last plain copy | The same without the 12-25 % copies | Before last copy, "
              "processed ones included |", "|---|---|---|---|---|"]
    table = []
    for n in names:
        vv = [r[n] for r in versions_all if r[n] != ""]

        def before(pairs):
            return sum(1 for x in vv if x <= max(r[n] for r in pairs if r[n] != ""))

        table.append((auc([r[n] for r in copies if r[n] != ""], vv), n, before(plain), before(plain_big),
                      before(copies), len(vv)))
    table.sort(key=lambda t: (-t[0], t[2]))
    for a_, n, b_plain, b_big, b_all, total in table:
        lines.append(f"| {n} | {a_:.4f} | {b_plain} ({100 * b_plain / total:.1f} %) | "
                     f"{b_big} ({100 * b_big / total:.1f} %) | {b_all} ({100 * b_all / total:.1f} %) |")
    lookup = {t[1]: t for t in table}
    lines += ["", "### AntiDupl's algorithms per setting", "",
              "Versions before the last plain copy, with / without the 12-25 % copies, per reduced size; the "
              "local colour difference is the planned algorithm of plan 02 (area resampling only).", "",
              "| Algorithm | Plane | Resampling | " + " | ".join(str(s) for s in sm.SIZES) + " |",
              "|---|---|---|" + "---|" * len(sm.SIZES)]
    for alg, label in (("ssim", "SSIM"), ("msd", "mean square")):
        for colour in ("gray", "colour"):
            for resample in ("bilinear", "area"):
                cells = ["{2} / {3}".format(*lookup[f"antidupl-{alg}-{colour}-{resample}-{s}"]) for s in sm.SIZES]
                lines.append(f"| {label} | {colour} | {resample} | " + " | ".join(cells) + " |")
    cells = ["{2} / {3}".format(*lookup[f"colour-block-{s}"]) if f"colour-block-{s}" in lookup else "-" for s in sm.SIZES]
    lines.append("| local colour | colour | area | " + " | ".join(cells) + " |")
    # The original against each kind of difference, all versions against them.
    by_group = {g: [] for g, _ in GROUPS}
    for r in rows:
        ia, ib = images[r["a"]], images[r["b"]]
        if ia["case"] != ib["case"] or "original" not in (ia["kind"], ib["kind"]):
            continue
        g = kind_of(ib if ia["kind"] == "original" else ia)
        if g in by_group:
            by_group[g].append(r)
    score = {}
    for n in names:
        vv = [r[n] for r in versions_all if r[n] != ""]
        for g, pairs in by_group.items():
            gv = [r[n] for r in pairs if r[n] != ""]
            if gv:
                score[(n, g)] = (auc(gv, vv), sum(1 for x in vv if x <= max(gv)))
    lines += ["", "### Best at each kind of difference", "",
              "The original against the copies of one kind (crops, overlays, greyscale and transforms are the "
              "user's call), each metric judged as above: AUC against all versions, and in brackets how many "
              "versions come before that kind's worst pair.", "",
              "| Kind | Pairs | Best five | Best AntiDupl setting |", "|---|---|---|---|"]
    for g, pairs in by_group.items():
        ranked = sorted((n for n in names if (n, g) in score), key=lambda n: (-score[(n, g)][0], score[(n, g)][1]))
        if not ranked:
            continue
        best = ", ".join(f"{n} {score[(n, g)][0]:.3f} ({score[(n, g)][1]})" for n in ranked[:5])
        own = next((n for n in ranked if n.startswith("antidupl-")), None)
        own_cell = f"{own} {score[(own, g)][0]:.3f} ({score[(own, g)][1]})" if own else "-"
        lines.append(f"| {g} | {len(pairs)} | {best} | {own_cell} |")
    groups = [g for g in by_group if by_group[g]]
    lines += ["", "| Metric | " + " | ".join(groups) + " |", "|---|" + "---|" * len(groups)]
    for n in names:
        cells = [f"{score[(n, g)][0]:.3f} ({score[(n, g)][1]})" if (n, g) in score else "-" for g in groups]
        lines.append(f"| {n} | " + " | ".join(cells) + " |")
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
    lines += ["", "### Version classes before the last plain copy (without the 12-25 % copies)", "",
              "| Metric | " + " | ".join(VERSION_CLASSES) + " |", "|---|" + "---|" * len(VERSION_CLASSES)]
    for n in names:
        t = max(r[n] for r in plain_big if r[n] != "")
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


def codec_of(img):
    ext = img["file"].rsplit(".", 1)[1].lower()
    return {"jpg": "jpeg", "jpeg": "jpeg", "webp": "webp", "avif": "avif", "jxl": "jxl"}.get(ext, "lossless")


def loss(img):
    """(scale, quality, generations, kept, codec) of a clean or cropped
    image; the original is lossless at full size."""
    if img["kind"] == "original":
        return 1.0, 100.0, 0, 1.0, "lossless"
    codec = codec_of(img)
    q = img["quality"]
    quality = 100.0 if codec == "lossless" else float(q) if q.replace(".", "").isdigit() else None
    return float(img["scale"]), quality, int(img["generations"]), float(img["kept"]), codec


def effective_quality(img, q, history):
    """The JPEG-equivalent quality of a file: the lower of its own JPEG
    table's and, with `history`, the strongest JPEG trace in its pixels
    (study_metrics.jpeg_history); 100 for a lossless file without such a
    trace; None for other lossy files (WebP, AVIF, JPEG XL), whose quality
    can't be read."""
    found = [v for v in (q["jpeg_quality"], q.get("history_q") if history else None) if v is not None]
    if found:
        return min(found)
    return 100.0 if codec_of(img) == "lossless" else None


def better_copy(i, j, images, quality, history=True):
    """Of two images of the same picture, the one judged better: more
    pixels (over 0.5 % apart); else the higher JPEG-equivalent quality
    (over 2 apart); at the same quality, both lossless, clearly more detail
    (an upscaled copy has less) and then the larger file; at the same lossy
    quality the smaller file, the one converted fewer times; a lossless
    file over one whose quality can't be read; else the larger file."""
    qi, qj = quality[i], quality[j]
    if abs(qi["pixels"] - qj["pixels"]) > 0.005 * max(qi["pixels"], qj["pixels"]):
        return i if qi["pixels"] > qj["pixels"] else j
    ei, ej = effective_quality(images[i], qi, history), effective_quality(images[j], qj, history)
    if ei is not None and ej is not None:
        if abs(ei - ej) > 2:
            return i if ei > ej else j
        if ei == ej == 100:
            if max(qi["detail"], qj["detail"]) > 1.25 * min(qi["detail"], qj["detail"]):
                return i if qi["detail"] > qj["detail"] else j
            return i if qi["size"] > qj["size"] else j
        return i if qi["size"] < qj["size"] else j
    if 100 in (ei, ej):
        return i if ei == 100 else j
    return i if qi["size"] > qj["size"] else j


# Copies converted again after a lossy step (study_set.py), and which file
# of a pair with one of them is better: (better stem, worse stem).
HISTORY_PAIRS = [("original", "jpeg-q60-to-png"), ("jpeg-q90", "jpeg-q60-to-png"), ("jpeg-q75", "jpeg-q60-to-png"),
                 ("original", "jpeg-q60-shifted-to-png"), ("jpeg-q75", "jpeg-q60-shifted-to-png"),
                 ("jpeg-q90", "jpeg-q45-to-q95"), ("jpeg-q60", "jpeg-q45-to-q95"), ("jpeg-q45", "jpeg-q45-to-q95"),
                 ("jpeg-q85", "jpeg-q85-to-webp-q80"), ("webp-q90", "jpeg-q85-to-webp-q80"),
                 ("original", "webp-q50-to-png"), ("webp-q90", "webp-q50-to-png"), ("webp-q75", "webp-q50-to-png")]
HISTORY_STEMS = {w for _, w in HISTORY_PAIRS}


def task_b(images, quality, lines):
    lines += ["", "## B. Which copy is worse", "",
              "Pairs of the same picture (original, copies, crops of one case) that differ in one way, so one is "
              "known to be worse: **compression** (same size, one more lossy: a lower quality of the same codec, "
              "more re-encodings, or lossy against the original), **resolution** (lossless, one smaller), **crop** "
              "(lossless, full size, one shows less), **web copy** (the original against a copy that is smaller and "
              "compressed), **upscaled** (the original and the copies shrunk and blown back up to full size: the "
              "same pixel count, less real detail), **lossy history** (copies converted again after a lossy step: "
              "a JPEG saved as PNG, also shifted by 3 px; a q45 JPEG re-saved at q95; a JPEG re-saved as WebP; a "
              "WebP saved as PNG; against files known to be better, `HISTORY_PAIRS`). Per indicator: the share of "
              "pairs where it ranks the worse one lower (ties count half); \"-\" where it has no value for those "
              "images.", ""]
    groups = {"compression": [], "resolution": [], "crop": [], "web copy": [], "upscaled": [], "lossy history": []}
    by_stem = {(img["case"], img["stem"]): i for i, img in enumerate(images)}
    for case in sorted({i["case"] for i in images}):
        for good, bad in HISTORY_PAIRS:
            if (case, good) in by_stem and (case, bad) in by_stem:
                groups["lossy history"].append((by_stem[(case, good)], by_stem[(case, bad)]))
        pool = [i for i, img in enumerate(images) if img["case"] == case and img["kind"] in ("original", "copy", "crop")
                and img["stem"] not in HISTORY_STEMS]
        for i, j in itertools.combinations(pool, 2):
            (sa, qa, ga, ka, ca), (sb, qb, gb, kb, cb) = loss(images[i]), loss(images[j])
            if None in (qa, qb):
                continue
            better = None
            stems = images[i]["stem"] + images[j]["stem"]
            if "upscale" in stems:
                if all(images[k]["kind"] == "original" or images[k]["stem"].startswith("upscale") for k in (i, j)):
                    better, kind = (i if sa > sb else j), "upscaled"
            elif sa == sb == 1 and ka == kb == 1:
                if ca == cb and ca != "lossless" and (qa, -ga) != (qb, -gb) and (qa >= qb) == (-ga >= -gb):
                    better, kind = (i if (qa, -ga) > (qb, -gb) else j), "compression"
                elif {ca, cb} & {"lossless"} and ca != cb and images[i if ca == "lossless" else j]["kind"] == "original":
                    better, kind = (i if ca == "lossless" else j), "compression"
            elif ca == cb == "lossless" and ka == kb == 1 and sa != sb and "bilinear" not in stems and "nearest" not in stems:
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
    for i, q in quality.items():
        q["effective"] = effective_quality(images[i], q, True)
    indicators = [("pixels", lambda v: v["pixels"], 1), ("file size", lambda v: v["size"], 1),
                  ("bytes per pixel", lambda v: v["bpp"], 1),
                  ("JPEG quality of the file's table", lambda v: v["jpeg_quality"], 1),
                  ("JPEG history: strongest JPEG trace in the pixels", lambda v: v.get("history_q"), 1),
                  ("effective JPEG quality (the lower of both; 100 lossless without a trace)",
                   lambda v: v["effective"], 1),
                  ("sharpness (Laplacian variance)", lambda v: v["sharpness"], 1),
                  ("detail (RMS lost when halved)", lambda v: v["detail"], 1),
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
    for history, label in ((False, "**rule** of `better_copy`, the file's format and JPEG table only"),
                           (True, "**rule** of `better_copy` with the JPEG history")):
        cells = []
        for k, pairs in groups.items():
            right = sum(1 for good, bad in pairs if better_copy(good, bad, images, quality, history) == good)
            cells.append(f"{100 * right / len(pairs):.0f} % ({right} of {len(pairs)})" if pairs else "-")
        lines.append(f"| {label} | " + " | ".join(cells) + " |")
    wrong = [(images[g]["case"], images[g]["stem"], images[b]["stem"]) for k, pairs in groups.items()
             for g, b in pairs if better_copy(g, b, images, quality, True) != g]
    lines += ["", "Pairs the rule with the JPEG history gets wrong (case, better, worse): "
              + ("; ".join(" ".join(w) for w in wrong) if wrong else "none") + "."]


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
    # The same judgement with OpenCV's ORB and AKAZE keypoints.
    def crop_by(r, method):
        if method == "sift":
            return crop_of(r)
        a, b, n = r.get(f"{method}-share-a", ""), r.get(f"{method}-share-b", ""), r.get(f"{method}-inliers", "")
        if "" in (a, b, n) or n < 15:
            return False
        return (b >= 0.95 and a < 0.97) or (a >= 0.95 and b < 0.97)
    keys = ("original~crop", "copy pairs", "version pairs", "unrelated")
    lines += ["", "Judged a crop, per keypoint method (ORB and AKAZE through OpenCV, same matching rules):", "",
              "| Method | " + " | ".join(keys) + " |", "|---|" + "---|" * len(keys)]
    for method in ("sift", "orb", "akaze"):
        cells = []
        for key in keys:
            g = groups.get(key, [])
            n = sum(1 for r in g if crop_by(r, method))
            cells.append(f"{n} ({100 * n / len(g):.0f} %)" if g else "-")
        lines.append(f"| {method.upper()} | " + " | ".join(cells) + " |")
    lines += ["", "| Crop | Kept (truth) | Kept (estimated, per case) | Rotation found |", "|---|---|---|---|"]
    for stem in ("crop-1", "crop-2", "crop-5", "crop-10", "crop-20", "crop-right-10", "crop-square", "crop-5-rescaled", "rotate-90", "mirror"):
        g = [r for r in rows if "original" in (images[r["a"]]["kind"], images[r["b"]]["kind"])
             and stem in (images[r["a"]]["stem"], images[r["b"]]["stem"]) and images[r["a"]]["case"] == images[r["b"]]["case"]]
        if not g:
            continue
        # The truth depends on the case for crop-square (its aspect ratio).
        truths = [float(images[r["a"]]["kept"] if images[r["a"]]["stem"] == stem else images[r["b"]]["kept"]) for r in g]
        truth = f"{truths[0]:.2f}" if len(set(truths)) == 1 else " ".join(f"{t:.2f}" for t in truths)
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


EXTRA = ["sift-inliers", "sift-matches", "share-a", "share-b", "align-scale", "align-rotation",
         "orb-inliers", "orb-share-a", "orb-share-b", "akaze-inliers", "akaze-share-a", "akaze-share-b"]


def read_rows(out, images):
    """pairs.csv back into rows (numbers as floats, blanks as ""), and the
    metric names in its column order."""
    index = {(img["case"], img["file"]): i for i, img in enumerate(images)}
    with open(os.path.join(out, "pairs.csv"), encoding="utf-8") as f:
        reader = csv.DictReader(f)
        header = reader.fieldnames
        names = header[header.index("changed") + 1:header.index("sift-inliers")]
        rows = []
        for r in reader:
            if (r["case_a"], r["a"]) not in index or (r["case_b"], r["b"]) not in index:
                continue
            row = {"a": index[(r["case_a"], r["a"])], "b": index[(r["case_b"], r["b"])],
                   "class": r["class"], "changed": r["changed"]}
            for k in names + EXTRA:
                row[k] = "" if r.get(k, "") == "" else float(r[k])
            rows.append(row)
    # Metrics computed by other tools (embed_metrics.py): pairs-*.csv,
    # joined on the pair.
    at = {(images[r["a"]]["case"], images[r["a"]]["file"], images[r["b"]]["case"], images[r["b"]]["file"]): r
          for r in rows}
    for extra in sorted(f for f in os.listdir(out) if f.startswith("pairs-") and f.endswith(".csv")):
        with open(os.path.join(out, extra), encoding="utf-8") as f:
            reader = csv.DictReader(f)
            more = reader.fieldnames[4:]
            for r in reader:
                row = at.get((r["case_a"], r["a"], r["case_b"], r["b"]))
                if row is not None:
                    for k in more:
                        row[k] = "" if r[k] == "" else float(r[k])
        for row in rows:
            for k in more:
                row.setdefault(k, "")
        names = names + more
    return rows, names


def read_quality(out, images):
    index = {(img["case"], img["file"]): i for i, img in enumerate(images)}
    quality = {}
    for r in csv.DictReader(open(os.path.join(out, "quality.csv"), encoding="utf-8")):
        i = index.get((r["case"], r["file"]))
        if i is None:
            continue
        quality[i] = {k: (None if r.get(k, "") in ("", "None") else float(r[k]))
                      for k in ("pixels", "size", "bpp", "jpeg_quality", "sharpness", "detail", "history_q",
                                "history_n", "blockiness", "blurring")}
    return quality


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("set")
    ap.add_argument("cache")
    ap.add_argument("out")
    ap.add_argument("--dll")
    ap.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 2) - 2))
    ap.add_argument("--no-slow", action="store_true")
    ap.add_argument("--cases", help="comma-separated case names (default: all)")
    ap.add_argument("--analysis-only", action="store_true",
                    help="only rewrite summary.md from pairs.csv and quality.csv in <out>")
    a = ap.parse_args()
    os.makedirs(a.cache, exist_ok=True)
    os.makedirs(a.out, exist_ok=True)
    with open(os.path.join(a.cache, "CACHEDIR.TAG"), "w", encoding="ascii", newline="\n") as f:
        f.write(TAG)
    images = load_set(a.set)
    if a.cases:
        images = [img for img in images if img["case"] in a.cases.split(",")]
    if not a.analysis_only:
        compute(a, images)
    rows, names = read_rows(a.out, images)
    quality = read_quality(a.out, images)
    lines = ["# Settings study summary", "", f"Generated by `settings_study.py`: {len(images)} images in "
             f"{len({i['case'] for i in images})} cases, {len(rows)} pairs.", ""]
    task_a(rows, names, images, lines)
    task_b(images, quality, lines)
    task_c(rows, images, lines)
    with open(os.path.join(a.out, "summary.md"), "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(lines) + "\n")
    print("summary written", flush=True)
    return 0


def compute(a, images):
    """Features, every pair's metrics (pairs.csv) and the per-image quality
    values (quality.csv)."""
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

    core = core_values(a.dll, a.set, sorted({img["case"] for img in images}), tmp) if a.dll else {}
    with ProcessPoolExecutor(a.workers) as pool:
        details = list(pool.map(sm.detail, [img["path"] for img in images], chunksize=1))
        histories = list(pool.map(sm.jpeg_history, [img["path"] for img in images], chunksize=1))
    with open(os.path.join(a.out, "quality.csv"), "w", encoding="utf-8", newline="") as fq:
        w = csv.writer(fq)
        w.writerow(["case", "file", "kind", "pixels", "size", "bpp", "jpeg_quality", "sharpness", "detail",
                    "history_q", "history_n", "blockiness", "blurring"])
        for i, img in enumerate(images):
            f = small[i]
            bl = core.get(os.path.normcase(os.path.abspath(img["path"])), (None, None))
            w.writerow([img["case"], img["file"], img["kind"], f["pixels"], os.path.getsize(img["path"]), f["bpp"],
                        f["jpeg_quality"], f["sharpness"], details[i], *histories[i], bl[0], bl[1]])

    names = metric_names(not a.no_slow)
    fields = ["case_a", "a", "case_b", "b", "class", "changed"] + names + EXTRA
    with open(os.path.join(a.out, "pairs.csv"), "w", encoding="utf-8", newline="") as fp:
        w = csv.DictWriter(fp, fields, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            out = dict(r)
            out["case_a"], out["case_b"] = images[r["a"]]["case"], images[r["b"]]["case"]
            out["a"], out["b"] = images[r["a"]]["file"], images[r["b"]]["file"]
            w.writerow(out)
    shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
