"""jpegQS (QuantSmooth) on the JPEG copies of the study set (plan 07): how
much each one gains, by SSIMULACRA2 against the original on a central
1024 px crop at full resolution (higher = closer to the original), with
jpegQS at -q 3 and -q 6, 3 iterations. Also a JPEG rebuilt from the PNG
of the q60 JPEG (re-encoded at q60 with the set's own encoder settings),
to see whether that PNG loses the jpegQS option.

Usage: py -3 qs_check.py <set> <work folder> <jpegqs64.exe> <ssimulacra2.exe>
The work folder receives the crops and jpegQS outputs (scratch).
"""
import io
import os
import subprocess
import sys

import numpy as np
from PIL import Image

Image.MAX_IMAGE_PIXELS = None
SET, WORK, QS, SSIMU = sys.argv[1:5]
FILES = ["jpeg-q30.jpg", "jpeg-q45.jpg", "jpeg-q60.jpg", "jpeg-q75.jpg", "jpeg-q85.jpg", "jpeg-q90.jpg",
         "jpeg-q95.jpg", "jpeg-q100.jpg", "jpeg-q85-x3.jpg", "jpeg-q45-to-q95.jpg"]


def crop(im, side=1024):
    w, h = im.size
    x0, y0 = (w - side) // 2, (h - side) // 2
    return im.convert("RGB").crop((x0, y0, x0 + side, y0 + side))


def score(ref_png, im, tag):
    path = os.path.join(WORK, tag + ".png")
    crop(im).save(path)
    out = subprocess.run([SSIMU, ref_png, path], capture_output=True, text=True).stdout.split()
    return float(out[-1])


def qs(src, dst, level):
    subprocess.run([QS, "-q", str(level), "-n", "3", "-i", "0", src, dst], check=True, capture_output=True)
    return Image.open(dst)


os.makedirs(WORK, exist_ok=True)
for case in sorted(os.listdir(SET)):
    folder = os.path.join(SET, case)
    if not os.path.isfile(os.path.join(folder, "manifest.tsv")):
        continue
    ref = os.path.join(WORK, f"{case}-ref.png")
    crop(Image.open(os.path.join(folder, "original.png"))).save(ref)
    print(f"== {case}  (SSIMULACRA2 against the original; QS -q 3 and -q 6, 3 iterations)")
    rows = []
    for f in FILES:
        src = os.path.join(folder, f)
        before = score(ref, Image.open(src), f"{case}-{f}")
        after3 = score(ref, qs(src, os.path.join(WORK, "qs3.jpg"), 3), f"{case}-{f}-qs3")
        after6 = score(ref, qs(src, os.path.join(WORK, "qs6.jpg"), 6), f"{case}-{f}-qs6")
        rows.append((f, before, after3, after6))
        print(f"{f:22} before {before:6.2f}  QS3 {after3:6.2f}  QS6 {after6:6.2f}", flush=True)
    # The PNG of the q60 JPEG, re-encoded at q60 with the set's settings.
    png = Image.open(os.path.join(folder, "jpeg-q60-to-png.png")).convert("RGB")
    buf = io.BytesIO()
    png.save(buf, "JPEG", quality=60, subsampling=2, optimize=True)
    rebuilt = os.path.join(WORK, "rebuilt.jpg")
    open(rebuilt, "wb").write(buf.getvalue())
    original_q60 = open(os.path.join(folder, "jpeg-q60.jpg"), "rb").read()
    a = np.asarray(Image.open(rebuilt).convert("RGB"), dtype=np.int16)
    b = np.asarray(Image.open(os.path.join(folder, "jpeg-q60.jpg")).convert("RGB"), dtype=np.int16)
    after = score(ref, qs(rebuilt, os.path.join(WORK, "qs3.jpg"), 3), f"{case}-rebuilt-qs3")
    print(f"rebuilt from the PNG:  bytes identical to jpeg-q60.jpg: {buf.getvalue() == original_q60}; "
          f"pixels differing: {100 * (a != b).any(axis=2).mean():.3f} % (max {np.abs(a - b).max()}); QS3 {after:6.2f}",
          flush=True)
