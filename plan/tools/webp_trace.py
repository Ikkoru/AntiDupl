"""The WebP trace (plan 07, "Which copy is worse"): calibration samples,
their measurements, and the analysis plan 07 quotes.

From each never-WebP picture of the set (originals, the artist's variants
and steps), a central square of up to 1024 px is saved as WebP at known
qualities (libwebp through Pillow at methods 4 and 6, and through
ImageMagick with sharp YUV), as JPEG -> WebP and WebP -> JPEG chains, and
as never-WebP copies (the picture itself, JPEG, AVIF, JPEG XL, resized,
upscaled, sharpened, blurred). Per sample:

* the change curve d20..d95: the RMS change of a central 512 px crop,
  aligned to the sample's 16 px macroblock grid, after a WebP re-encode
  (Pillow, method 4) at each quality from 20 to 95;
* the grid profile p0..p15: the mean absolute luma step between
  neighbouring columns and rows by position modulo 16 (VP8 codes 4x4
  blocks, JPEG 8x8 ones).

--analyze reads that CSV and validates two detectors and one quality
estimate, leaving one illustration out at a time; each detector's
threshold is the highest never-WebP score of the other illustrations:

* curve: the step ratios d_q / d_(q-5) in log, minus their median over
  the never-WebP samples; a WebP at Q drops more than usual into Q and
  then stays flatter: score(Q) = -excess(into Q) + mean excess of Q's
  step and the two after; the best Q is the quality estimate;
* grid: the profile folded to 8 positions; from its Fourier magnitudes
  relative to the mean, W = |P2| - (|P1| + |P3|) / 2: VP8's two edges per
  8 px add up in P2 and cancel in P1 and P3, JPEG's one edge puts the
  same in all, a 2x upscale's alternation only in P4.

Usage: py -3 webp_trace.py <set> <out.csv> [--workers N]
       py -3 webp_trace.py --analyze <out.csv>

LIBJXL (folder of cjxl/djxl, else PATH) and ImageMagick's magick on PATH.
"""
import argparse
import collections
import csv
import io
import os
import subprocess
import sys
import tempfile
from concurrent.futures import ProcessPoolExecutor

import numpy as np
from PIL import Image, ImageFilter

Image.MAX_IMAGE_PIXELS = None
QS = list(range(20, 100, 5))
SIDE = 1024
CROP = 512
LIBJXL = os.environ.get("LIBJXL", "")


def tool(name):
    return os.path.join(LIBJXL, name + ".exe") if LIBJXL else name


def decode(data):
    return Image.open(io.BytesIO(data)).convert("RGB")


def encoded(im, fmt, **options):
    buf = io.BytesIO()
    im.save(buf, fmt, **options)
    return buf.getvalue()


def magick_webp(im, q):
    """libwebp with sharp YUV (RGB to YUV with less colour bleeding at
    edges), as cwebp -sharp_yuv, through ImageMagick."""
    out = subprocess.run(["magick", "png:-", "-quality", str(q), "-define", "webp:method=4",
                          "-define", "webp:use-sharp-yuv=true", "webp:-"],
                         input=encoded(im, "PNG", compress_level=1), capture_output=True, check=True)
    return decode(out.stdout)


def jxl(im, distance, scratch):
    src, enc, dec = (os.path.join(scratch, n) for n in ("in.png", "out.jxl", "out.png"))
    im.save(src, compress_level=1)
    subprocess.run([tool("cjxl"), src, enc, "-d", str(distance), "--quiet"], check=True, capture_output=True)
    subprocess.run([tool("djxl"), enc, dec, "--quiet"], check=True, capture_output=True)
    return Image.open(dec).convert("RGB")


def samples(im, scratch):
    """(family, encoder, WebP quality or "", description, image)."""
    webp = lambda src, q, m=4: decode(encoded(src, "WEBP", quality=q, method=m))
    jpeg = lambda src, q: decode(encoded(src, "JPEG", quality=q))
    out = [("webp", "pillow-m4", q, f"webp q{q}", webp(im, q)) for q in QS]
    for q in (20, 35, 50, 65, 80, 95):
        out.append(("webp", "pillow-m6", q, f"webp m6 q{q}", webp(im, q, 6)))
        out.append(("webp", "magick-sharp", q, f"webp sharp-yuv q{q}", magick_webp(im, q)))
    for q in (50, 80):
        out.append(("chain", "pillow-m4", q, f"jpeg q85 -> webp q{q}", webp(jpeg(im, 85), q)))
    for q in (90, 95):
        out.append(("chain", "pillow-m4", 50, f"webp q50 -> jpeg q{q}", jpeg(webp(im, 50), q)))
    out.append(("never", "", "", "the picture", im))
    out += [("never", "jpeg", "", f"jpeg q{q}", jpeg(im, q)) for q in (30, 50, 70, 90, 95)]
    out += [("never", "avif", "", f"avif q{q}", decode(encoded(im, "AVIF", quality=q))) for q in (40, 60, 80)]
    out += [("never", "jxl", "", f"jpeg xl d{d}", jxl(im, d, scratch)) for d in (1, 2.5, 4)]
    w, h = im.size
    out.append(("never", "resize", "", "75 % lanczos", im.resize((w * 3 // 4, h * 3 // 4), Image.LANCZOS)))
    out.append(("never", "resize", "", "50 % then x2", im.resize((w // 2, h // 2), Image.LANCZOS).resize((w, h), Image.LANCZOS)))
    out.append(("never", "processed", "", "sharpened", im.filter(ImageFilter.UnsharpMask(2, 80, 2))))
    out.append(("never", "processed", "", "blurred 1 px", im.filter(ImageFilter.GaussianBlur(1))))
    return out


def curve(im):
    w, h = im.size
    x0, y0 = (w - CROP) // 2 // 16 * 16, (h - CROP) // 2 // 16 * 16
    crop = im.crop((x0, y0, x0 + CROP, y0 + CROP))
    a = np.asarray(crop, dtype=np.float64)
    d = []
    for q in QS:
        b = np.asarray(decode(encoded(crop, "WEBP", quality=q, method=4)), dtype=np.float64)
        d.append(float(np.sqrt(((a - b) ** 2).mean())))
    return d


def profile16(im):
    a = np.asarray(im, dtype=np.float64)
    y = 0.299 * a[..., 0] + 0.587 * a[..., 1] + 0.114 * a[..., 2]
    p = np.zeros(16)
    for g in (np.abs(np.diff(y, axis=1)).mean(axis=0), np.abs(np.diff(y, axis=0)).mean(axis=1)):
        n = len(g) // 16 * 16
        p += g[:n].reshape(-1, 16).mean(axis=0)
    return list(p)


def job(img):
    im = Image.open(img["path"]).convert("RGB")
    w, h = im.size
    side = min(SIDE, min(w, h) // 16 * 16)
    x0, y0 = (w - side) // 2 // 16 * 16, (h - side) // 2 // 16 * 16
    im = im.crop((x0, y0, x0 + side, y0 + side))
    with tempfile.TemporaryDirectory() as scratch:
        return [[img["case"], img["stem"], img["kind"], family, encoder, q, detail] + curve(s) + profile16(s)
                for family, encoder, q, detail, s in samples(im, scratch)]


# ----------------------------------------------------------------- analysis

def band(q):
    return "q20-45" if q < 50 else "q50-70" if q < 75 else "q75-85" if q < 90 else "q90-95"


def analyze(path):
    rows = list(csv.DictReader(open(path, encoding="utf-8")))
    for r in rows:
        d = np.array([float(r[f"d{q}"]) for q in QS])
        r["lr"] = np.log(np.maximum(d[1:], 1e-6) / np.maximum(d[:-1], 1e-6))  # the step into QS[k + 1]
        p16 = np.array([float(r[f"p{i}"]) for i in range(16)])
        P = np.abs(np.fft.fft(p16[:8] + p16[8:]))
        P /= P[0]
        r["W"] = P[2] - (P[1] + P[3]) / 2
        r["q"] = int(r["webp_q"]) if r["webp_q"] else None
        r["group"] = (("never", r["sample"]) if r["family"] == "never"
                      else (f"webp {r['encoder']}", band(r["q"])) if r["family"] == "webp" else ("chain", r["sample"]))
    cases = sorted({r["case"] for r in rows})
    found = {"curve": collections.Counter(), "grid": collections.Counter()}
    close = collections.Counter()
    total = collections.Counter()
    false = {"curve": [], "grid": []}
    for test in cases:
        train = [r for r in rows if r["case"] != test]
        base = np.median(np.array([r["lr"] for r in train if r["family"] == "never"]), axis=0)

        def best(r):
            ex = r["lr"] - base
            s = {QS[k + 1]: -ex[k] + ex[k:k + 3].mean() for k in range(len(ex))}
            q = max(s, key=s.get)
            return s[q], q
        t_curve = max(best(r)[0] for r in train if r["family"] == "never")
        t_grid = max(r["W"] for r in train if r["family"] == "never")
        for r in rows:
            if r["case"] != test:
                continue
            g = r["group"]
            total[g] += 1
            score, q = best(r)
            found["curve"][g] += score > t_curve
            found["grid"][g] += r["W"] > t_grid
            if r["q"] is not None:
                close[g] += abs(q - r["q"]) <= 5
            if r["family"] == "never":
                false["curve"] += [r] if score > t_curve else []
                false["grid"] += [r] if r["W"] > t_grid else []
    never = sum(n for g, n in total.items() if g[0] == "never")
    print(f"Left-out illustrations: {len(cases)}; never-WebP samples {never}, with a false trace: "
          f"curve {len(false['curve'])}, grid {len(false['grid'])}.")
    print(f"\n{'WebP samples':52s} {'n':>4} {'curve finds':>12} {'grid finds':>11} {'curve quality within 5':>23}")
    for g in sorted(total):
        if g[0] != "never":
            n = total[g]
            print(f"{g[0] + ' ' + g[1]:52s} {n:4d} {100 * found['curve'][g] / n:11.0f} % {100 * found['grid'][g] / n:10.0f} % "
                  f"{100 * close[g] / n:22.0f} %")
    for name in ("curve", "grid"):
        kinds = collections.Counter(r["sample"] for r in false[name])
        print(f"\nnever-WebP samples with a false {name} trace, by kind: " + (", ".join(f"{k} {n}" for k, n in kinds.most_common()) or "none"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("set", nargs="?")
    ap.add_argument("out")
    ap.add_argument("--workers", type=int, default=os.cpu_count())
    ap.add_argument("--analyze", action="store_true")
    a = ap.parse_args()
    if a.analyze:
        analyze(a.out)
        return 0
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import settings_study as ss
    sources = [i for i in ss.load_set(a.set) if i["kind"] in ("original", "variant", "step")]
    with open(a.out, "w", encoding="utf-8", newline="") as f:
        out = csv.writer(f)
        out.writerow(["case", "source", "source_kind", "family", "encoder", "webp_q", "sample"]
                     + [f"d{q}" for q in QS] + [f"p{i}" for i in range(16)])
        with ProcessPoolExecutor(a.workers) as pool:
            for n, rows in enumerate(pool.map(job, sources), 1):
                out.writerows(rows)
                f.flush()
                print(f"{n}/{len(sources)} {rows[0][0]} {rows[0][1]}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
