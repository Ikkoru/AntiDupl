"""Reproduce AntiDupl's "Difference" for image pairs, before and after the planned fixes.

Usage:
    python repro_difference.py [--size N] "A.jpg" "B.jpg" ["C.jpg" "D.jpg" ...]

--size is AntiDupl's "Reduced image size" (default here 128, the user's
setting; AntiDupl's own default is 32).

For each pair prints:
  * which decoder the current build uses for each file (TurboJPEG only if the file starts FF D8 FF E0)
  * the Difference the current build shows (R/B-swapped gray on the TurboJPEG path + float32 SSIM)
  * the Difference after fix 1 (TJPF_BGRA + every JPEG through TurboJPEG) and fix 2 (exact/double SSIM)
  * whether the decoded full-resolution pixels are identical

Expected on the user's Examples.zip:
  Identical but 0.22 -> current 0.2175 (shows 0.22), fixed 0 (pixel-identical)
  Identical but 0.08 -> current 0.0765 (shows 0.08), fixed 0 (pixel-identical)
  Different but 0.00 -> current 0.0005 (shows 0.00), fixed ~0.00025 (not pixel-identical)
With --size 32 the current build shows 0.18 / 0.07 / 0.00 for the same pairs.
"""
import sys
import numpy as np
from adsim import (load_rgb, starts_with_jfif, current_gray, gray_correct, reduced,
                   antidupl_ssim_difference, fixed_ssim_difference)


def main(paths):
    size = 128
    if len(paths) >= 2 and paths[0] == "--size":
        size, paths = int(paths[1]), paths[2:]
    if len(paths) < 2 or len(paths) % 2:
        print(__doc__)
        return 1
    for a, b in zip(paths[0::2], paths[1::2]):
        ra, rb = load_rgb(a), load_rgb(b)
        cur, _ = antidupl_ssim_difference(reduced(current_gray(a, ra), size), reduced(current_gray(b, rb), size))
        fixed = fixed_ssim_difference(reduced(gray_correct(ra), size), reduced(gray_correct(rb), size))
        same_pixels = ra.shape == rb.shape and np.array_equal(ra, rb)
        dec = lambda p: "TurboJPEG (R/B swapped)" if starts_with_jfif(p) else "GDI+"
        print(f"{a}\n{b}")
        print(f"  decoders now      : {dec(a)} | {dec(b)}")
        print(f"  current build     : {cur:.6f}  (column shows {cur:.2f})")
        print(f"  after fixes       : {fixed:.6f}")
        print(f"  pixel-identical   : {same_pixels}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
