"""Show that the current SSIM arithmetic often gives a non-zero Difference for IDENTICAL planes.

Usage:
    python float_noise.py image1.jpg [image2.png ...]

Takes random crops of the given images, builds 128x128 planes and compares each plane
with itself. Any result > 0 is a pair that
  * is shown as "0.00" but not bold/green (ResultRowSetter requires difference == 0), and
  * is dropped when "Threshold difference" = 0 % (IsDuplPair requires difference <= 0).
Observed on the user's examples: ~31 % of self-comparisons -> 7.63e-06 or 1.526e-05.
"""
import sys
import numpy as np
from PIL import Image
from adsim import load_rgb, gray_correct, antidupl_ssim_difference, fixed_ssim_difference


def main(paths, n=3000, seed=1):
    if not paths:
        print(__doc__)
        return 1
    rng = np.random.default_rng(seed)
    grays = [gray_correct(load_rgb(p)) for p in paths]
    bad = 0
    values = set()
    for k in range(n):
        g = grays[k % len(grays)]
        H, W = g.shape
        h, w = rng.integers(64, H), rng.integers(64, W)
        y, x = rng.integers(0, H - h + 1), rng.integers(0, W - w + 1)
        p = np.asarray(Image.fromarray(g[y:y + h, x:x + w]).resize((128, 128), Image.BILINEAR))
        d, _ = antidupl_ssim_difference(p, p)
        assert fixed_ssim_difference(p, p) == 0.0
        if d > 0:
            bad += 1
            values.add(round(d, 9))
    print(f"{bad} of {n} self-comparisons ({100 * bad / n:.1f} %) give Difference > 0 with the current code")
    print(f"distinct non-zero values: {sorted(values)}")
    print("fixed_ssim_difference(): 0 for all of them")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
