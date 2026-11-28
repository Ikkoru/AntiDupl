"""Restoring a palette image (GIF, PNG8) within its own constraint (T40a),
as jpegQS restores a JPEG within its steps. Each pixel's colour before
quantising lay in its palette entry's cell (the colours nearer that entry
than any other), so the picture may be smoothed only as far as each pixel
stays in its cell: the result quantises back to the same file. A
dithered file has no such cell per pixel (its error was pushed to the
neighbours), so it is only smoothed freely.

Per study original (reduced by area to a quarter, a central 512 px crop),
quantised by Pillow to 256, 64 and 16 colours, plain and Floyd-Steinberg
dithered; prints SSIMULACRA2 against the crop before quantising, as
stored, after edge-preserving smoothing (OpenCV's bilateral filter, colour
sigma 10 and 25, four rounds) free, and kept in the cells.

    py -3 palette_smooth.py <set> <work folder> --ssimulacra2 <ssimulacra2.exe>

OpenCV through STUDY_PYLIB, as for settings_study.py.
"""
import argparse
import os
import subprocess
import sys

import numpy as np
from PIL import Image
from scipy.spatial import cKDTree

if os.environ.get("STUDY_PYLIB"):
    sys.path.insert(0, os.environ["STUDY_PYLIB"])
import cv2  # noqa: E402

Image.MAX_IMAGE_PIXELS = None


def study_cases(set_dir):
    """The set's illustration cases: the folders with a manifest and an
    original (the photo and hand-added folders have neither)."""
    return sorted(d for d in os.listdir(set_dir)
                  if os.path.isfile(os.path.join(set_dir, d, "manifest.tsv"))
                  and os.path.isfile(os.path.join(set_dir, d, "original.png")))


def project(x, idx, pal, tree):
    """Each pixel pulled back towards its own entry until no other entry is
    nearer: on the segment from the entry to x, the farthest point still in
    the cell (cells are convex, so a bisection finds it)."""
    p = pal[idx]
    lo, hi = np.zeros(idx.shape), np.ones(idx.shape)

    def inside(t):
        _, near = tree.query((p + (x - p) * t[..., None]).reshape(-1, 3))
        return near.reshape(idx.shape) == idx

    lo[inside(hi)] = 1
    for _ in range(8):
        mid = (lo + hi) / 2
        m = inside(mid)
        lo, hi = np.where(m, mid, lo), np.where(m, hi, mid)
    return p + (x - p) * lo[..., None]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("set")
    ap.add_argument("work")
    ap.add_argument("--ssimulacra2", required=True)
    ap.add_argument("--cases", help="comma-separated; default: every case of the set")
    a = ap.parse_args()
    os.makedirs(a.work, exist_ok=True)

    def s2(ref, x):
        pa, pb = os.path.join(a.work, "ref.png"), os.path.join(a.work, "x.png")
        Image.fromarray(ref).save(pa)
        Image.fromarray(np.clip(np.round(x), 0, 255).astype(np.uint8)).save(pb)
        return float(subprocess.run([a.ssimulacra2, pa, pb], capture_output=True, text=True).stdout.split()[-1])

    for case in (a.cases.split(",") if a.cases else study_cases(a.set)):
        im = Image.open(os.path.join(a.set, case, "original.png")).convert("RGB")
        im = im.resize((im.width // 4, im.height // 4), Image.Resampling.BOX)
        w, h = im.size
        ref = np.asarray(im.crop((w // 2 - 256, h // 2 - 256, w // 2 + 256, h // 2 + 256)))
        for colours in (256, 64, 16):
            base = Image.fromarray(ref).quantize(colours)
            for dither in (Image.Dither.NONE, Image.Dither.FLOYDSTEINBERG):
                # Pillow dithers only against a given palette.
                q = Image.fromarray(ref).quantize(colours, palette=base, dither=dither)
                pal = np.array(q.getpalette()[:3 * colours], float).reshape(-1, 3)
                tree = cKDTree(pal)
                # A palette can hold one colour twice: each index becomes the
                # entry the tree finds for its colour, or no pixel would ever
                # count as inside its own cell.
                idx = tree.query(pal)[1][np.asarray(q)]
                stored = pal[idx]
                line = [f"{case} {colours:3d} colours {'dithered' if dither else 'plain':8s}: stored {s2(ref, stored):6.2f}"]
                for sigma in (10, 25):
                    smooth = lambda z: cv2.bilateralFilter(z.astype(np.float32), 5, sigma, 3).astype(np.float64)
                    cell = f""
                    if dither == Image.Dither.NONE:
                        x = stored.copy()
                        for _ in range(4):
                            x = project(smooth(x), idx, pal, tree)
                        cell = f", in cells {s2(ref, x):6.2f}"
                    line.append(f"sigma {sigma}: free {s2(ref, smooth(stored)):6.2f}{cell}")
                print("; ".join(line), flush=True)


if __name__ == "__main__":
    main()
