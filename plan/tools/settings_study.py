"""Settings study (plan 07): for every pair of images in a study set, the
difference each comparison setting gives, and how well each setting keeps
copies (to delete) apart from versions (to keep).

Usage: py -3 settings_study.py <set folder> <output folder> [--workers N]

<set folder> is study_set.py's output (one folder per artwork and
manifest.tsv). Writes to <output folder>:
    pairs.csv    one row per pair: files, class, changed area, and a column
                 per setting
    summary.md   per setting, with the threshold set just high enough to
                 find every copy: how many versions of each class it would
                 pair up wrongly; then each class's range per setting

Settings: algorithm x reduced size x colour x resampling.
    ssim      AntiDupl's SSIM (one window over the reduced image), exact
              arithmetic as in the core since #248
    msd       AntiDupl's mean square difference, sqrt(mean d^2) / 255, in %
    block     worst 4x4-block colour RMS in % (plan 02, mode 3), always
              colour and area-resampled
    size      16, 32, 64, 128 (AntiDupl's choices)
    colour    gray: AntiDupl's grey plane; colour: the same per B, G, R
              plane, SSIM averaged over the planes, MSD over all values
    resample  bilinear: AntiDupl's pipeline (bilinear to 256, then 2x2
              reductions); area: box filter straight to the size (plan 01 G)

Pair classes (pairs within one artwork; "clean" = the original or one of
its copies):
    copy                original~copy, copy~copy: to be found
    sketch, wip-far, wip-close
                        clean~step: the first quarter of the steps, the
                        middle, the last quarter
    variant-minor, variant-medium, variant-major
                        clean~variant and variant~variant: under 1 %, 1-5 %,
                        5 % or more of the picture changed (any channel by
                        more than 24, against the original for clean~variant)
    edit-minor, edit-medium, edit-major
                        clean~edit: sign and bar; mosaic and local recolour;
                        global recolour
    gray, crop          clean~gray, clean~crop: reported, counted in
                        neither group, since whether they are copies is the
                        user's call
    other               the rest (step~step, variant~step, ...): not counted
    unrelated           different artworks
"""
import argparse
import csv
import itertools
import os
import re
import sys
from concurrent.futures import ProcessPoolExecutor

import numpy as np
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import adsim  # noqa: E402

Image.MAX_IMAGE_PIXELS = None
SIZES = [16, 32, 64, 128]
C1, C2 = (0.01 * 255) ** 2, (0.03 * 255) ** 2
VERSION_CLASSES = ["sketch", "wip-far", "wip-close", "variant-minor", "variant-medium", "variant-major",
                   "edit-minor", "edit-medium", "edit-major"]
REPORTED = ["gray", "crop"]
EDIT_CLASS = {"sign": "edit-minor", "bar": "edit-minor", "mosaic": "edit-medium",
              "recolour-local": "edit-medium", "recolour-global": "edit-major"}


def planes(path):
    """Reduced planes of one image: {(colour, resample, size): [planes]}."""
    rgb = np.asarray(Image.open(path).convert("RGB"))
    gray = adsim.gray_correct(rgb)
    channels = [rgb[..., 2], rgb[..., 1], rgb[..., 0]]  # B, G, R as AntiDupl's BGRA
    out = {}
    for colour, chans in (("gray", [gray]), ("colour", channels)):
        bil = [adsim.resize_bilinear(np.ascontiguousarray(c), 256, 256) for c in chans]
        size = 256
        while size > SIZES[0]:
            bil = [adsim.reduce2x2(p) for p in bil]
            size //= 2
            if size in SIZES:
                out[(colour, "bilinear", size)] = bil
        for s in SIZES:
            out[(colour, "area", s)] = [np.asarray(Image.fromarray(np.ascontiguousarray(c)).resize((s, s), Image.BOX))
                                        for c in chans]
    small = rgb[:: max(1, rgb.shape[0] // 512), :: max(1, rgb.shape[1] // 512)]  # for the changed-area estimate
    return out, rgb.shape[:2], small


def ssim(a, b):
    x, y = a.astype(np.float64), b.astype(np.float64)
    mx, my = x.mean(), y.mean()
    vx, vy = x.var(), y.var()
    cov = (x * y).mean() - mx * my
    res = (2 * mx * my + C1) * (2 * cov + C2) / ((mx * mx + my * my + C1) * (vx + vy + C2))
    return max(0.0, 100.0 * (1.0 - res))


def msd(pa, pb):
    d = np.concatenate([(a.astype(np.float64) - b.astype(np.float64)).ravel() for a, b in zip(pa, pb)])
    return float(np.sqrt((d * d).mean()) / 255 * 100)


def block(pa, pb):
    d2 = sum((a.astype(np.float64) - b.astype(np.float64)) ** 2 for a, b in zip(pa, pb)) / len(pa)
    s = d2.shape[0] // 4
    blocks = d2.reshape(s, 4, s, 4).mean(axis=(1, 3))
    return float(np.sqrt(blocks.max()) / 255 * 100)


def settings():
    for alg in ("ssim", "msd"):
        for colour in ("gray", "colour"):
            for resample in ("bilinear", "area"):
                for s in SIZES:
                    yield f"{alg}-{colour}-{resample}-{s}", alg, colour, resample, s
    for s in (32, 64, 128):
        yield f"block-colour-area-{s}", "block", "colour", "area", s


def changed_area(sa, sb, shape_a, shape_b):
    """Share of the picture where the two differ visibly (any channel by
    more than 24), on a ~512 px sample; None for images of other sizes."""
    if shape_a != shape_b or sa.shape != sb.shape:
        return None
    return float((np.abs(sa.astype(np.int16) - sb.astype(np.int16)).max(axis=2) > 24).mean())


def variant_class(changed):
    return "variant-minor" if changed < 0.01 else "variant-medium" if changed < 0.05 else "variant-major"


def step_class(detail):
    i, n = map(int, re.match(r"step (\d+) of (\d+)", detail).groups())
    return "sketch" if i <= n / 4 else "wip-close" if i > n * 3 / 4 else "wip-far"


def pair_class(ma, mb, changed, original_changed):
    """ma, mb: manifest rows; changed: the pair's changed area;
    original_changed: {(artwork, variant file): changed area against the
    original}."""
    if ma["artwork"] != mb["artwork"]:
        return "unrelated"
    kinds = {ma["kind"], mb["kind"]}
    clean = {"original", "copy"}
    if kinds <= clean:
        return "copy"
    if kinds == {"variant"}:
        return variant_class(changed)
    (c, v) = (ma, mb) if ma["kind"] in clean else (mb, ma)
    if c["kind"] not in clean:
        return "other"
    if v["kind"] == "variant":
        return variant_class(original_changed[(v["artwork"], v["file"])])
    if v["kind"] == "step":
        return step_class(v["detail"])
    if v["kind"] == "edit":
        return EDIT_CLASS[v["file"].rsplit(".", 1)[0]]
    return v["kind"]  # gray, crop


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("set")
    ap.add_argument("out")
    ap.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 2) - 1))
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    rows = list(csv.DictReader(open(os.path.join(a.set, "manifest.tsv"), encoding="utf-8"), delimiter="\t"))
    paths = [os.path.join(a.set, r["artwork"], r["file"]) for r in rows]
    with ProcessPoolExecutor(a.workers) as pool:
        data = list(pool.map(planes, paths, chunksize=1))
    print(f"{len(rows)} images reduced", flush=True)

    original_changed = {}
    for i, r in enumerate(rows):
        if r["kind"] == "variant":
            o = next(j for j, q in enumerate(rows) if q["artwork"] == r["artwork"] and q["kind"] == "original")
            original_changed[(r["artwork"], r["file"])] = changed_area(data[o][2], data[i][2], data[o][1], data[i][1])

    cols = list(settings())
    out_rows = []
    for i, j in itertools.combinations(range(len(rows)), 2):
        ma, mb = rows[i], rows[j]
        (pa, shape_a, sa), (pb, shape_b, sb) = data[i], data[j]
        changed = changed_area(sa, sb, shape_a, shape_b) if ma["artwork"] == mb["artwork"] else None
        cls = pair_class(ma, mb, changed, original_changed)
        row = {"artwork": ma["artwork"] if ma["artwork"] == mb["artwork"] else f"{ma['artwork']}/{mb['artwork']}",
               "first": ma["file"], "second": mb["file"], "class": cls,
               "changed": "" if changed is None else f"{changed:.4f}"}
        for name, alg, colour, resample, s in cols:
            p1, p2 = pa[(colour, resample, s)], pb[(colour, resample, s)]
            if alg == "ssim":
                v = sum(ssim(x, y) for x, y in zip(p1, p2)) / len(p1)
            elif alg == "msd":
                v = msd(p1, p2)
            else:
                v = block(p1, p2)
            row[name] = f"{v:.6f}"
        out_rows.append(row)
    fields = ["artwork", "first", "second", "class", "changed"] + [c[0] for c in cols]
    with open(os.path.join(a.out, "pairs.csv"), "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fields)
        w.writeheader()
        w.writerows(out_rows)
    print(f"{len(out_rows)} pairs", flush=True)
    write_summary(out_rows, cols, os.path.join(a.out, "summary.md"))
    return 0


def caught_table(out_rows, cols, counts, copy_filter):
    lines = ["| Setting | Threshold | Versions caught | " + " | ".join(VERSION_CLASSES + REPORTED) + " | unrelated |",
             "|---|---|---|" + "---|" * (len(VERSION_CLASSES) + len(REPORTED) + 1)]
    table = []
    for name, *_ in cols:
        t = max(float(r[name]) for r in out_rows if r["class"] == "copy" and copy_filter(r))
        caught = {c: sum(1 for r in out_rows if r["class"] == c and float(r[name]) <= t)
                  for c in VERSION_CLASSES + REPORTED + ["unrelated"]}
        table.append((sum(caught[c] for c in VERSION_CLASSES), name, t, caught))
    table.sort(key=lambda x: (x[0], x[1]))
    for total, name, t, caught in table:
        lines.append(f"| {name} | {t:.4f} | {total} of {sum(counts[c] for c in VERSION_CLASSES)} | " +
                     " | ".join(f"{caught[c]}" for c in VERSION_CLASSES + REPORTED + ["unrelated"]) + " |")
    return lines


def write_summary(out_rows, cols, path):
    counts = {c: sum(1 for r in out_rows if r["class"] == c) for c in VERSION_CLASSES + REPORTED + ["copy", "unrelated"]}
    lines = ["# Settings study summary", "",
             "Generated by `settings_study.py`; values in % like AntiDupl's Difference column.", "",
             f"Pairs: {counts['copy']} copy, " + ", ".join(f"{counts[c]} {c}" for c in VERSION_CLASSES + REPORTED) +
             f", {counts['unrelated']} unrelated.", "",
             "## With the threshold set to find every copy", "",
             "Threshold = the highest copy pair's value. Each class column: how many of its pairs fall at or below "
             "it, so would be paired up as duplicates. Versions = all classes from sketch to edit-major.", ""]
    lines += caught_table(out_rows, cols, counts, lambda r: True)
    lines += ["", "## The same without the 25 % copy", "",
              "The copy shrunk to a quarter sets the threshold of every setting; here it is left out, so the "
              "threshold finds the copies at 50 % size and more.", ""]
    lines += caught_table(out_rows, cols, counts, lambda r: "resize-25" not in r["first"] + r["second"])
    lines += ["", "## Ranges per class", "",
              "Per setting: min / median / max of each class.", ""]
    classes = ["copy"] + VERSION_CLASSES + REPORTED + ["unrelated"]
    lines += ["| Setting | " + " | ".join(classes) + " |", "|---|" + "---|" * len(classes)]
    for name, *_ in cols:
        cells = []
        for c in classes:
            vals = sorted(float(r[name]) for r in out_rows if r["class"] == c)
            cells.append(f"{vals[0]:.3g} / {vals[len(vals) // 2]:.3g} / {vals[-1]:.3g}" if vals else "-")
        lines.append(f"| {name} | " + " | ".join(cells) + " |")
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(lines) + "\n")


if __name__ == "__main__":
    sys.exit(main())
