"""The pair preview's perceptual marks on saved pairs through a build's core,
without and with alignment: per pair, the fragments of the default 16 x 16 grid
whose largest map value exceeds the threshold, as MarkedFragments marks them.

Usage: py -3 highlight_check.py PAIRS_DIR DLL_DIR N[,N...] [--pictures DIR]
                                [--threshold T]

PAIRS_DIR  one folder per pair, named by its number, holding its two images
           (decision_pairs.py's pairs folder)
DLL_DIR    a build with adAlignedDifferenceMaps
--pictures writes one sheet per pair: both images with the plain marks on top,
           with the aligned ones below
Prints per pair whether it aligned, the marks without and with alignment (per
image, which differ when the framing does), and the map's largest values.
"""
import argparse
import ctypes
import os

import numpy as np
from PIL import Image, ImageDraw, ImageFile

ImageFile.LOAD_TRUNCATED_IMAGES = True
Image.MAX_IMAGE_PIXELS = None
GRID = 16
SIZE = 512
MAP_SIDE = 768  # ResultsOptions.PERCEPTUAL_DIFFERENCE_SIZE
ARGB32 = 1


class Bitmap(ctypes.Structure):
    _fields_ = [("width", ctypes.c_uint32), ("height", ctypes.c_uint32), ("stride", ctypes.c_int32),
                ("format", ctypes.c_int32), ("data", ctypes.c_void_p)]


def map_size(w, h):
    s = min(1.0, MAP_SIDE / max(w, h))
    return max(8, round(w * s)), max(8, round(h * s))


def marks(m, w, h, threshold):
    f = SIZE // GRID
    out = []
    for r in range(GRID):
        for c in range(GRID):
            x0, y0 = c * f * w // SIZE, r * f * h // SIZE
            x1, y1 = max(x0 + 1, (c + 1) * f * w // SIZE), max(y0 + 1, (r + 1) * f * h // SIZE)
            if m[y0:y1, x0:x1].size and m[y0:y1, x0:x1].max() > threshold:
                out.append((c, r))
    return out


def tile(im, cells):
    s = 480 / max(im.size)
    im = im.resize((max(1, round(im.width * s)), max(1, round(im.height * s))), Image.BOX).convert("RGB")
    d = ImageDraw.Draw(im)
    for c, r in cells:
        x0, y0 = c * im.width / GRID, r * im.height / GRID
        d.rectangle([x0, y0, x0 + im.width / GRID, y0 + im.height / GRID], outline=(255, 0, 0), width=1)
    return im


def sheet(tiles):
    top, bottom = tiles[:2], tiles[2:]
    width = max(sum(t.width for t in row) + 8 for row in (top, bottom))
    height = max(t.height for t in top) + max(t.height for t in bottom) + 8
    out = Image.new("RGB", (width, height), (40, 40, 40))
    y = 0
    for row in (top, bottom):
        out.paste(row[0], (0, y))
        out.paste(row[1], (row[0].width + 8, y))
        y += max(t.height for t in row) + 8
    return out


def main():
    p = argparse.ArgumentParser()
    p.add_argument("pairs")
    p.add_argument("dll")
    p.add_argument("numbers")
    p.add_argument("--pictures")
    p.add_argument("--threshold", type=float, default=12.0)
    a = p.parse_args()
    core = ctypes.CDLL(os.path.join(a.dll, "AntiDupl.dll"))
    bp = ctypes.POINTER(Bitmap)
    core.adDifferenceMap.argtypes = [bp, bp, ctypes.c_uint32, ctypes.c_uint32, ctypes.c_void_p]
    core.adAlignedDifferenceMaps.argtypes = [bp, bp, ctypes.c_uint32, ctypes.c_uint32, ctypes.c_void_p,
                                             ctypes.c_uint32, ctypes.c_uint32, ctypes.c_void_p, ctypes.POINTER(ctypes.c_int32)]
    print("pair  aligned  plain marks  aligned marks  largest plain, aligned")
    for n in a.numbers.split(","):
        folder = os.path.join(a.pairs, n)
        ims = [Image.open(os.path.join(folder, f)).convert("RGB") for f in sorted(os.listdir(folder))]
        pixels = []
        for im in ims:
            rgb = np.asarray(im)
            pixels.append(np.ascontiguousarray(np.dstack([rgb[:, :, 2], rgb[:, :, 1], rgb[:, :, 0], np.full(rgb.shape[:2], 255, np.uint8)])))
        bitmaps = [Bitmap(x.shape[1], x.shape[0], x.shape[1] * 4, ARGB32, x.ctypes.data) for x in pixels]
        s1, s2 = map_size(*ims[0].size), map_size(*ims[1].size)
        plain = np.zeros((s1[1], s1[0]), np.float32)
        if core.adDifferenceMap(ctypes.byref(bitmaps[0]), ctypes.byref(bitmaps[1]), s1[0], s1[1], plain.ctypes.data):
            raise SystemExit(f"adDifferenceMap refused pair {n}")
        m1, m2 = np.zeros((s1[1], s1[0]), np.float32), np.zeros((s2[1], s2[0]), np.float32)
        aligned = ctypes.c_int32(0)
        if core.adAlignedDifferenceMaps(ctypes.byref(bitmaps[0]), ctypes.byref(bitmaps[1]), s1[0], s1[1], m1.ctypes.data,
                                        s2[0], s2[1], m2.ctypes.data, ctypes.byref(aligned)):
            raise SystemExit(f"adAlignedDifferenceMaps refused pair {n}")
        plain_marks = marks(plain, *s1, a.threshold)
        if aligned.value:
            c1, c2 = marks(m1, *s1, a.threshold), marks(m2, *s2, a.threshold)
            print(f"{n:>5}  yes  {len(plain_marks):4}  {len(c1):4} {len(c2):4}  {plain.max():7.2f} {m1.max():7.2f}", flush=True)
        else:
            c1 = c2 = plain_marks
            print(f"{n:>5}  no   {len(plain_marks):4}  (plain)    {plain.max():7.2f}", flush=True)
        if a.pictures:
            os.makedirs(a.pictures, exist_ok=True)
            sheet([tile(ims[0], plain_marks), tile(ims[1], plain_marks), tile(ims[0], c1), tile(ims[1], c2)]).save(os.path.join(a.pictures, f"{n}.png"))


if __name__ == "__main__":
    main()
