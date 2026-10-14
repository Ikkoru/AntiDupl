"""jpegQS (QuantSmooth) on the JPEG copies of the study set (plan 07): how
much each one gains against the picture before JPEG (the original, or for
a reduced copy the PNG of the same reduction), on a central crop of at
most 1024 px at the file's own size, with jpegQS at -q 3 and -q 6, 3
iterations. Two measures: SSIMULACRA2 (higher = closer) and Butteraugli's
3-norm (lower = closer). Also a JPEG rebuilt from the PNG of the q60 JPEG
(re-encoded at q60 with the set's own encoder settings), to see whether
that PNG loses the jpegQS option.

Usage: py -3 qs_check.py <set> <work folder> <jpegqs64.exe> <libjxl bin folder>
The work folder receives the crops and jpegQS outputs (scratch).
"""
import io
import os
import re
import subprocess
import sys

import numpy as np
from PIL import Image

Image.MAX_IMAGE_PIXELS = None
SET, WORK, QS, LIBJXL = sys.argv[1:5]
# (file, its reference before JPEG)
FILES = [(f"jpeg-q{q}.jpg", "original.png") for q in (30, 45, 60, 75, 85, 90, 95, 100)] + \
        [("jpeg-q85-x3.jpg", "original.png"), ("jpeg-q45-to-q95.jpg", "original.png"),
         ("scale-50-jpeg-q85.jpg", "scale-50.png"), ("scale-50-jpeg-q60.jpg", "scale-50.png"),
         ("scale-25-jpeg-q75.jpg", "scale-25.png"), ("scale-25-jpeg-q60.jpg", "scale-25.png"),
         ("scale-25-jpeg-q45.jpg", "scale-25.png"), ("scale-12-jpeg-q60.jpg", "scale-12.png")]


def crop(im):
    w, h = im.size
    side = min(1024, w, h)
    x0, y0 = (w - side) // 2, (h - side) // 2
    return im.convert("RGB").crop((x0, y0, x0 + side, y0 + side))


def measure(ref_png, im, tag):
    path = os.path.join(WORK, tag + ".png")
    crop(im).save(path)
    s2 = subprocess.run([os.path.join(LIBJXL, "ssimulacra2.exe"), ref_png, path], capture_output=True, text=True)
    ba = subprocess.run([os.path.join(LIBJXL, "butteraugli_main.exe"), ref_png, path, "--pnorm", "3"],
                        capture_output=True, text=True)
    norm3 = re.search(r"3-norm:\s*([0-9.]+)", ba.stdout + ba.stderr)
    return float(s2.stdout.split()[-1]), float(norm3.group(1)) if norm3 else float("nan")


def qs(src, dst, level):
    subprocess.run([QS, "-q", str(level), "-n", "3", "-i", "0", src, dst], check=True, capture_output=True)
    return Image.open(dst)


os.makedirs(WORK, exist_ok=True)
for case in sorted(os.listdir(SET)):
    folder = os.path.join(SET, case)
    if not os.path.isfile(os.path.join(folder, "manifest.tsv")):
        continue
    print(f"== {case}  (SSIMULACRA2 up is better / Butteraugli 3-norm down is better; before, QS -q 3, QS -q 6)")
    refs = {}
    for f, ref in FILES:
        if ref not in refs:
            refs[ref] = os.path.join(WORK, f"{case}-ref-{ref}")
            crop(Image.open(os.path.join(folder, ref))).save(refs[ref])
        src = os.path.join(folder, f)
        b = measure(refs[ref], Image.open(src), f"{case}-{f}")
        q3 = measure(refs[ref], qs(src, os.path.join(WORK, "qs3.jpg"), 3), f"{case}-{f}-qs3")
        q6 = measure(refs[ref], qs(src, os.path.join(WORK, "qs6.jpg"), 6), f"{case}-{f}-qs6")
        w, h = Image.open(src).size
        print(f"{f:22} {w:4}x{h:<4}  SSIMU2 {b[0]:6.2f} {q3[0]:6.2f} {q6[0]:6.2f}   "
              f"BA3 {b[1]:5.3f} {q3[1]:5.3f} {q6[1]:5.3f}", flush=True)
    png = Image.open(os.path.join(folder, "jpeg-q60-to-png.png")).convert("RGB")
    buf = io.BytesIO()
    png.save(buf, "JPEG", quality=60, subsampling=2, optimize=True)
    rebuilt = os.path.join(WORK, "rebuilt.jpg")
    open(rebuilt, "wb").write(buf.getvalue())
    a = np.asarray(Image.open(rebuilt).convert("RGB"), dtype=np.int16)
    b = np.asarray(Image.open(os.path.join(folder, "jpeg-q60.jpg")).convert("RGB"), dtype=np.int16)
    after = measure(refs["original.png"], qs(rebuilt, os.path.join(WORK, "qs3.jpg"), 3), f"{case}-rebuilt-qs3")
    print(f"rebuilt from the PNG: pixels differing from jpeg-q60.jpg {100 * (a != b).any(axis=2).mean():.3f} % "
          f"(max {np.abs(a - b).max()}); QS -q 3: SSIMU2 {after[0]:6.2f} BA3 {after[1]:5.3f}", flush=True)
