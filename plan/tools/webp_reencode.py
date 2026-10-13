"""Does re-encoding as WebP show where a file was WebP-compressed before
(plan 07, the WebP trace)? Prints, per file, the RMS change of a central
768 px crop (aligned to WebP's 16 px macroblocks) after a WebP re-encode
at each quality from 20 to 95: a file that was WebP at quality Q changes
little from Q up, one never saved as WebP keeps changing.

Usage: py -3 webp_reencode.py <folder> <file> [<file> ...]
"""
import io
import os
import sys

import numpy as np
from PIL import Image

Image.MAX_IMAGE_PIXELS = None
QS = list(range(20, 100, 5))


def curve(path, side=768):
    im = Image.open(path).convert("RGB")
    w, h = im.size
    x0, y0 = (w - side) // 2 // 16 * 16, (h - side) // 2 // 16 * 16
    crop = im.crop((x0, y0, x0 + side, y0 + side))
    a = np.asarray(crop, dtype=np.float64)
    out = []
    for q in QS:
        buf = io.BytesIO()
        crop.save(buf, "WEBP", quality=q, method=4)
        b = np.asarray(Image.open(io.BytesIO(buf.getvalue())).convert("RGB"), dtype=np.float64)
        out.append(np.sqrt(((a - b) ** 2).mean()))
    return out


print("file".ljust(26), " ".join(f"{q:>5}" for q in QS))
for name in sys.argv[2:]:
    c = curve(os.path.join(sys.argv[1], name))
    print(name[:26].ljust(26), " ".join(f"{v:5.2f}" for v in c))
