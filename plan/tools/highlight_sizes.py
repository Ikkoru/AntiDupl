"""The perceptual highlight at several map sizes on the real runs' pairs
scored by threshold_sizes.py: per size and highlight threshold, how many
copies (acted on, aligned 768 score up to 12) get any mark, and how many
kept versions (mistakes, any score up to 50) get none; with the time per
pair. Marks as highlight_check counts them (16 x 16 grid; a pair has a mark
when its map's largest value is over the threshold), aligned where the pair
aligns and on the plain map where it doesn't, as the preview does. A
version with any mark counts as found, whether or not the mark is on what
differs.

    py -3 highlight_sizes.py <threshold_sizes work dir> <bin\\Release> <sides,...> [thresholds,...]

The thresholds default to 12, the preview's default.
"""
import csv
import ctypes
import os
import sys
import time

import numpy as np
from PIL import Image, ImageFile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import highlight_check as hc

ImageFile.LOAD_TRUNCATED_IMAGES = True
Image.MAX_IMAGE_PIXELS = None
work, dll, sides = sys.argv[1], sys.argv[2], [int(s) for s in sys.argv[3].split(",")]
thresholds = [float(t) for t in sys.argv[4].split(",")] if len(sys.argv) > 4 else [12.0]
core = ctypes.CDLL(os.path.join(dll, "AntiDupl.dll"))
bp = ctypes.POINTER(hc.Bitmap)
core.adAlignedDifferenceMaps.argtypes = [bp, bp, ctypes.c_uint32, ctypes.c_uint32, ctypes.c_void_p,
                                         ctypes.c_uint32, ctypes.c_uint32, ctypes.c_void_p, ctypes.POINTER(ctypes.c_int32)]
core.adDifferenceMap.argtypes = [bp, bp, ctypes.c_uint32, ctypes.c_uint32, ctypes.c_void_p]
rows = list(csv.DictReader(open(os.path.join(work, "scores.tsv"), encoding="utf-8"), delimiter="\t"))


def num(v):
    return float(v) if v else None


copies = [r["id"] for r in rows if r["decision"] not in ("mistake", "left") and num(r["aligned-768"]) is not None and num(r["aligned-768"]) <= 12]
versions = [r["id"] for r in rows if r["decision"] == "mistake" and any(num(r[c]) is not None for c in r if "-" in c)]
print(len(copies), "copies,", len(versions), "kept versions", flush=True)

loaded = {}


def load(pair):
    folder = os.path.join(work, "pairs", pair)
    ims = [Image.open(os.path.join(folder, f)).convert("RGB") for f in sorted(os.listdir(folder))]
    px = []
    for im in ims:
        rgb = np.asarray(im)
        px.append(np.ascontiguousarray(np.dstack([rgb[:, :, 2], rgb[:, :, 1], rgb[:, :, 0], np.full(rgb.shape[:2], 255, np.uint8)])))
    return ims, px


def marked(pair, side):
    try:
        ims, px = load(pair)
    except Exception:          # formats PIL can't read (HEIC): left out
        return None, 0
    bms = [hc.Bitmap(x.shape[1], x.shape[0], x.shape[1] * 4, hc.ARGB32, x.ctypes.data) for x in px]
    s1, s2 = hc.map_size(*ims[0].size, side), hc.map_size(*ims[1].size, side)
    m1, m2 = np.zeros((s1[1], s1[0]), np.float32), np.zeros((s2[1], s2[0]), np.float32)
    aligned = ctypes.c_int32(0)
    t = time.perf_counter()
    if core.adAlignedDifferenceMaps(ctypes.byref(bms[0]), ctypes.byref(bms[1]), s1[0], s1[1], m1.ctypes.data,
                                    s2[0], s2[1], m2.ctypes.data, ctypes.byref(aligned)):
        return None, 0
    if not aligned.value:      # as PerceptualFragments: one plain map for both
        if core.adDifferenceMap(ctypes.byref(bms[0]), ctypes.byref(bms[1]), s1[0], s1[1], m1.ctypes.data):
            return None, 0
    t = time.perf_counter() - t
    # hc.marks finds a cell over the threshold exactly when the map's
    # largest value is: the cells cover the whole map.
    return float(m1.max()), t


for side in sides:
    out = {}
    for name, group in (("copies", copies), ("versions", versions)):
        counts, times = [], []
        for pair in group:
            n, t = marked(pair, side)
            if n is not None:
                counts.append(n)
                times.append(t)
        out[name] = counts
        out[name + "-t"] = times
    c, v = out["copies"], out["versions"]
    if side == sides[0]:
        print(f"left out (unreadable or refused): {len(copies) - len(c)} copies, {len(versions) - len(v)} versions")
    t = out["copies-t"] + out["versions-t"]
    print(f"{side:5}: median {np.median(t) * 1000:.0f} ms, 90 % {np.percentile(t, 90) * 1000:.0f} ms", flush=True)
    for threshold in thresholds:
        print(f"       threshold {threshold:4g}: copies marked {sum(1 for x in c if x > threshold)}/{len(c)},"
              f" versions unmarked {sum(1 for x in v if x <= threshold)}/{len(v)}", flush=True)
