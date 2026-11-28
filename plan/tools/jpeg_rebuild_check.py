"""Checks jpeg_from_pixels (T40b): each study original's central 1024 px
crop saved as JPEG by libjpeg-turbo (Pillow) at several qualities, 4:2:0
and 4:4:4, decoded to lossless pixels by Pillow and by djpeg -nosmooth
(chroma repeated, not filtered), as is and with 3 px left and 5 px top cut
(off the block grid); then rebuilt from those pixels. Prints, per file:
the chroma layout and qualities read; the share of the non-zero
coefficients rebuilt exactly, with the true tables given and with the
tables read; and SSIMULACRA2 against the crop before JPEG of the pixels,
of jpegQS on the real JPEG and of jpegQS on the rebuilt one.

    py -3 jpeg_rebuild_check.py <set> <work folder> --jpegcoef <jpegcoef.exe>
        --jpegqs <jpegqs64.exe> --ssimulacra2 <ssimulacra2.exe> --djpeg <djpeg.exe>
        [--cases a,b] [--qualities 30,50,...]
"""
import argparse
import os
import subprocess
import sys

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "jpegcoef"))
import jpegcoef  # noqa: E402
import jpeg_from_pixels as jfp  # noqa: E402

Image.MAX_IMAGE_PIXELS = None
SIDE = 1024
CROP = (3, 5)


def study_cases(set_dir):
    """The set's illustration cases: the folders with a manifest and an
    original (the photo and hand-added folders have neither)."""
    return sorted(d for d in os.listdir(set_dir)
                  if os.path.isfile(os.path.join(set_dir, d, "manifest.tsv"))
                  and os.path.isfile(os.path.join(set_dir, d, "original.png")))


def nz_exact(ref, j, bx, by, sub):
    """Per component, the share of coefficients non-zero in either file
    that the rebuilt one has exactly, the rebuilt grid starting at pixel
    (bx, by) of the real file."""
    out = []
    for k, (a, b) in enumerate(zip(ref["components"], j["components"])):
        s = 1 if k == 0 else sub
        ca = a["coefs"][by // (8 * s):, bx // (8 * s):]
        cb = b["coefs"]
        hb, wb = min(ca.shape[0], cb.shape[0]), min(ca.shape[1], cb.shape[1])
        ca, cb = ca[:hb, :wb], cb[:hb, :wb]
        nz = (ca != 0) | (cb != 0)
        out.append(100 * np.mean(ca[nz] == cb[nz]) if nz.any() else float("nan"))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("set")
    ap.add_argument("work")
    ap.add_argument("--jpegcoef", required=True)
    ap.add_argument("--jpegqs", required=True)
    ap.add_argument("--ssimulacra2", required=True)
    ap.add_argument("--djpeg", required=True)
    ap.add_argument("--cases", help="comma-separated; default: every case of the set")
    ap.add_argument("--qualities", default="30,50,60,75,85,90,95")
    a = ap.parse_args()
    os.makedirs(a.work, exist_ok=True)

    def s2(ref, rgb):
        pa, pb = os.path.join(a.work, "ref.png"), os.path.join(a.work, "x.png")
        Image.fromarray(ref).save(pa)
        Image.fromarray(rgb.astype(np.uint8)).save(pb)
        return float(subprocess.run([a.ssimulacra2, pa, pb], capture_output=True, text=True).stdout.split()[-1])

    def qs(jpg):
        out = os.path.join(a.work, "qs.jpg")
        subprocess.run([a.jpegqs, "-q", "3", "-n", "3", "-i", "0", jpg, out], check=True, capture_output=True)
        return np.asarray(Image.open(out).convert("RGB"))

    print("case sub q decoder crop | layout read, true; qualities read | non-zero exact Y Cb Cr, tables given | "
          "the same, tables read | SSIMULACRA2: pixels, jpegQS on the JPEG, jpegQS on the rebuilt")
    for case in (a.cases.split(",") if a.cases else study_cases(a.set)):
        im = Image.open(os.path.join(a.set, case, "original.png")).convert("RGB")
        x0, y0 = (im.width - SIDE) // 2 // 16 * 16, (im.height - SIDE) // 2 // 16 * 16
        src = np.asarray(im.crop((x0, y0, x0 + SIDE, y0 + SIDE)))
        for sub, subname in ((2, "420"), (0, "444")):
            for q in (int(v) for v in a.qualities.split(",")):
                jpg = os.path.join(a.work, f"{case}-{subname}-q{q}.jpg")
                Image.fromarray(src).save(jpg, quality=q, subsampling=sub)
                ref = jpegcoef.read_jpeg(jpg, a.jpegcoef)
                tref = (ref["tables"][ref["components"][0]["table"]], ref["tables"][ref["components"][1]["table"]])
                real_qs = qs(jpg)
                ppm = os.path.join(a.work, "nosmooth.ppm")
                subprocess.run([a.djpeg, "-nosmooth", "-outfile", ppm, jpg], check=True)
                decoded = {"pillow": np.asarray(Image.open(jpg).convert("RGB")),
                           "nosmooth": np.asarray(Image.open(ppm).convert("RGB"))}
                for dec, full in decoded.items():
                    for crop in ((0, 0), CROP):
                        rgb = full[crop[1]:, crop[0]:]
                        j1, off1, how1, _ = jfp.rebuild(rgb, "auto", tref)
                        j2, off2, how2, qual = jfp.rebuild(rgb, "auto", None)
                        e1 = nz_exact(ref, j1, off1[0] + crop[0], off1[1] + crop[1], 1 if how1 == "444" else 2)
                        bx, by = off2[0] + crop[0], off2[1] + crop[1]
                        e2 = nz_exact(ref, j2, bx, by, 1 if how2 == "444" else 2)
                        rebuilt = os.path.join(a.work, "rebuilt.jpg")
                        jpegcoef.write_jpeg(j2, rebuilt, a.jpegcoef)
                        h, w = j2["height"], j2["width"]
                        region = src[by:by + h, bx:bx + w]
                        print(f"{case} {subname} q{q} {dec:8s} {crop[0]},{crop[1]} | {how2:7s} {'444' if sub == 0 else '420':3s} {qual} | "
                              f"{e1[0]:6.2f} {e1[1]:6.2f} {e1[2]:6.2f} | {e2[0]:6.2f} {e2[1]:6.2f} {e2[2]:6.2f} | "
                              f"{s2(region, rgb[off2[1]:off2[1] + h, off2[0]:off2[0] + w]):6.2f} "
                              f"{s2(region, real_qs[by:by + h, bx:bx + w]):6.2f} {s2(region, qs(rebuilt)):6.2f}", flush=True)


if __name__ == "__main__":
    main()
