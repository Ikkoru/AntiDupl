"""ird (Li et al., "Image Resampling Detection via Spectral Correlation
with False Alarm Control", github.com/li-yanhao/ird) asked one question
about a larger image (T37, plan 08): its log10 NFA at the distance a
resampling from a given smaller size would leave (the larger's width or
height less the smaller's, within 2 %), per axis, and its lowest log10
NFA anywhere with the distance there (the larger's size less that
distance is the size it was resampled from). The rank-transform
preprocessing; ird's own bar for it is -5.

    <python> -I -B ird_check.py --ird <ird clone> [--pylib <folder>] <larger> <width> <height>
    <python> -I -B ird_check.py --ird <ird clone> [--pylib <folder>] --pairs <run>\\pairs <n>...

<python> needs numpy, scipy, numba, torch, joblib, PyYAML and scikit-image
(--pylib adds a folder of packages to the path, for those it lacks).
--pairs takes each numbered pair folder's two images, the larger asked
about the smaller's size.
"""
import argparse
import os
import sys

import numpy as np
from PIL import Image

Image.MAX_IMAGE_PIXELS = None


def luma(path):
    a = np.asarray(Image.open(path).convert("RGB"), dtype=np.float64)
    return 0.299 * a[..., 0] + 0.587 * a[..., 1] + 0.114 * a[..., 2]


def ask(detect, path, small_size, tol=0.02):
    """Per axis (horizontal, vertical): (log10 NFA at the smaller's size,
    lowest log10 NFA, its distance)."""
    img = luma(path)
    jpeg = path.lower().endswith((".jpg", ".jpeg"))
    out = []
    for axis, direction, small in ((1, "horizontal", small_size[0]), (0, "vertical", small_size[1])):
        n = img.shape[axis]
        nfa = detect(img, preproc="rt", preproc_param={"rt_size": 3}, window_ratio=0.10, nb_neighbor=20,
                     direction=direction, is_jpeg=jpeg, is_demosaic=False, max_distance=n - 1)
        lg = np.log10(nfa + 1e-50)
        d, slack = n - small, int(tol * small)
        at = float(lg[max(1, d - slack):d + slack + 1].min()) if d > 1 else 0.0
        low = int(np.argmin(lg[1:]) + 1)
        out.append((at, float(lg[low]), low))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ird", required=True)
    ap.add_argument("--pylib")
    ap.add_argument("--pairs")
    ap.add_argument("rest", nargs="+")
    a = ap.parse_args()
    if a.pylib:
        sys.path.insert(0, a.pylib)
    sys.path.insert(0, a.ird)
    from src.ird import detect_resampling  # noqa: E402  (ird's own package)

    def report(label, path, small):
        (ah, lh, dh), (av, lv, dv) = ask(detect_resampling, path, small)
        print(f"{label}: at the smaller's size h {ah:.1f} v {av:.1f} | lowest h {lh:.1f} at {dh}, v {lv:.1f} at {dv}", flush=True)

    if a.pairs:
        for n in a.rest:
            folder = os.path.join(a.pairs, n)
            ims = sorted(((f, Image.open(os.path.join(folder, f)).size) for f in os.listdir(folder)),
                         key=lambda t: t[1][0] * t[1][1])
            (_, small), (large, size) = ims[0], ims[-1]
            report(f"{n} {small}->{size}", os.path.join(folder, large), small)
    else:
        path, w, h = a.rest
        report(path, path, (int(w), int(h)))


if __name__ == "__main__":
    main()
