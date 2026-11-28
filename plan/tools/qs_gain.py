"""How much jpegQS restores (T40), over JPEG quality, picture size and
chroma subsampling. Per original (each case folder's original.png in the
study set), reduced by area to 100/50/25/12 % of its size, a central crop
of at most 1024 px of that reduction, saved as JPEG by libjpeg-turbo
(Pillow) at qualities 20-95 and both subsamplings; then SSIMULACRA2 and
Butteraugli's 3-norm against the crop before JPEG, for the JPEG and for
jpegQS at -q 3 and -q 6 (3 iterations). Appends to a TSV and skips rows
it already has.

    py -3 qs_gain.py <set> <work folder> <out.tsv> --jpegqs <jpegqs64.exe>
        --libjxl <folder with ssimulacra2.exe, butteraugli_main.exe>
    py -3 qs_gain.py --summary <out.tsv>
    py -3 qs_gain.py --axes <work folder> [--jpeg2png <jpeg2png.exe>]

--summary prints the median gain per quality and size, and the effective
quality: the plain-JPEG quality whose SSIMULACRA2 the jpegQS result
reaches, read off the same crop's curve over quality (100 when it passes
the curve's top).

--axes measures a restoration on two axes the user sees separately
(plan 08), on the work folder's files: fine detail (the Laplacian's error
on the original's strongest Laplacian pixels, the top 5 %, over the
original's own there) and blocks (how much more the picture jumps across
the 8 px block edges than inside the blocks, beyond the original's own),
and places jpegQS -q 6's result, and with --jpeg2png jpeg2png's (written
beside them as -j2p.png), on each axis's plain-JPEG curve.
"""
import argparse
import csv
import os
import re
import statistics
import subprocess

import numpy as np
from PIL import Image

Image.MAX_IMAGE_PIXELS = None
SCALES = (100, 50, 25, 12)
QUALITIES = range(20, 100, 5)


def study_cases(set_dir):
    """The set's illustration cases: the folders with a manifest and an
    original (the photo and hand-added folders have neither)."""
    return sorted(d for d in os.listdir(set_dir)
                  if os.path.isfile(os.path.join(set_dir, d, "manifest.tsv"))
                  and os.path.isfile(os.path.join(set_dir, d, "original.png")))


COLS = ["case", "scale", "sub", "quality", "pixels", "bytes", "s2_jpeg", "s2_qs3", "s2_qs6", "ba_jpeg", "ba_qs3", "ba_qs6"]


def metrics(libjxl, ref, path):
    s2 = subprocess.run([os.path.join(libjxl, "ssimulacra2.exe"), ref, path], capture_output=True, text=True)
    ba = subprocess.run([os.path.join(libjxl, "butteraugli_main.exe"), ref, path, "--pnorm", "3"],
                        capture_output=True, text=True)
    m = re.search(r"3-norm:\s*([0-9.]+)", ba.stdout + ba.stderr)
    return float(s2.stdout.split()[-1]), float(m.group(1)) if m else float("nan")


def measure(a):
    done = set()
    if os.path.exists(a.out):
        with open(a.out, encoding="utf-8") as f:
            done = {tuple(r[c] for c in COLS[:4]) for r in csv.DictReader(f, delimiter="\t")}
    os.makedirs(a.work, exist_ok=True)
    new = not os.path.exists(a.out)
    with open(a.out, "a", encoding="utf-8", newline="") as out:
        if new:
            out.write("\t".join(COLS) + "\n")
        for case in study_cases(a.set):
            orig = Image.open(os.path.join(a.set, case, "original.png")).convert("RGB")
            for scale in SCALES:
                im = orig if scale == 100 else orig.resize((orig.width * scale // 100, orig.height * scale // 100),
                                                           Image.Resampling.BOX)
                side = min(1024, im.width, im.height) // 16 * 16
                x0, y0 = (im.width - side) // 2 // 16 * 16, (im.height - side) // 2 // 16 * 16
                im = im.crop((x0, y0, x0 + side, y0 + side))
                ref = os.path.join(a.work, f"{case}-{scale}.png")
                im.save(ref)
                for sub, subname in ((2, "420"), (0, "444")):
                    for q in QUALITIES:
                        if (case, str(scale), subname, str(q)) in done:
                            continue
                        stem = os.path.join(a.work, f"{case}-{scale}-{subname}-q{q}")
                        im.save(stem + ".jpg", quality=q, subsampling=sub)
                        row = {"case": case, "scale": scale, "sub": subname, "quality": q, "pixels": side * side,
                               "bytes": os.path.getsize(stem + ".jpg")}
                        Image.open(stem + ".jpg").convert("RGB").save(stem + ".png")
                        row["s2_jpeg"], row["ba_jpeg"] = metrics(a.libjxl, ref, stem + ".png")
                        for level in (3, 6):
                            qs = f"{stem}-qs{level}"
                            subprocess.run([a.jpegqs, "-q", str(level), "-n", "3", "-i", "0", stem + ".jpg", qs + ".jpg"],
                                           check=True, capture_output=True)
                            Image.open(qs + ".jpg").convert("RGB").save(qs + ".png")
                            row[f"s2_qs{level}"], row[f"ba_qs{level}"] = metrics(a.libjxl, ref, qs + ".png")
                        out.write("\t".join(str(row[c]) for c in COLS) + "\n")
                        out.flush()
                        print(case, scale, subname, q, round(row["s2_jpeg"], 2), round(row["s2_qs6"], 2), flush=True)


def luma(path):
    a = np.asarray(Image.open(path).convert("RGB"), dtype=np.float64)
    return 0.299 * a[..., 0] + 0.587 * a[..., 1] + 0.114 * a[..., 2]


class Axes:
    """The two axes against one original (see --axes)."""

    def __init__(self, original):
        from scipy import ndimage
        self.nd = ndimage
        self.o = original
        self.lo = ndimage.laplace(original)
        self.lines = np.abs(self.lo) >= np.percentile(np.abs(self.lo), 95)
        self.own_blocks = self.block_excess(original)

    @staticmethod
    def block_excess(g):
        dx, dy = np.abs(np.diff(g, axis=1)), np.abs(np.diff(g, axis=0))
        ex, ey = (np.arange(dx.shape[1]) % 8) == 7, (np.arange(dy.shape[0]) % 8) == 7
        return dx[:, ex].mean() - dx[:, ~ex].mean() + dy[ey].mean() - dy[~ey].mean()

    def __call__(self, x):
        err = self.nd.laplace(x) - self.lo
        detail = np.sqrt(np.mean(err[self.lines] ** 2)) / np.sqrt(np.mean(self.lo[self.lines] ** 2))
        return detail, max(0.0, self.block_excess(x) - self.own_blocks)


def place(v, curve):
    """The plain quality with value v on a curve that falls with quality
    (lower = closer to the original); 100 past its best."""
    c = np.minimum.accumulate(np.array(curve))
    if v <= c[-1]:
        return 100.0
    if v >= c[0]:
        return float(QUALITIES[0])
    return float(np.interp(-v, -c, np.array(QUALITIES, float)))


def axes(work, jpeg2png):
    found = {}
    for f in os.listdir(work):
        m = re.fullmatch(r"(.+)-(\d+)-(420|444)-q20\.jpg", f)
        if m:
            found[(m.group(1), m.group(2), m.group(3))] = True
    table = {}
    for case, scale, sub in sorted(found):
        stem = os.path.join(work, f"{case}-{scale}-{sub}")
        measure_axes = Axes(luma(os.path.join(work, f"{case}-{scale}.png")))
        plain = [measure_axes(luma(f"{stem}-q{q}.png")) for q in QUALITIES]
        for q in QUALITIES:
            kinds = {"jpegQS": f"{stem}-q{q}-qs6.png"}
            if jpeg2png:
                out = f"{stem}-q{q}-j2p.png"
                if not os.path.exists(out):
                    subprocess.run([jpeg2png, f"{stem}-q{q}.jpg", "-o", out, "-f"], check=True, capture_output=True)
                kinds["jpeg2png"] = out
            for kind, path in kinds.items():
                d, b = measure_axes(luma(path))
                table.setdefault((kind, scale, q), []).append(
                    (place(d, [p[0] for p in plain]), place(b, [p[1] for p in plain])))
    for kind in ("jpegQS", "jpeg2png"):
        if not any(k[0] == kind for k in table):
            continue
        print(f"{kind}: the plain quality its result equals on fine detail / on blocks, median over the pictures and subsamplings")
        for scale in sorted({k[1] for k in table}, key=lambda s: -int(s)):
            cells = [f"q{q}:{statistics.median(v[0] for v in table[(kind, scale, q)]):.0f}/"
                     f"{statistics.median(v[1] for v in table[(kind, scale, q)]):.0f}" for q in QUALITIES]
            print(f"  {scale:>3} %  " + " ".join(cells))


def summary(path):
    with open(path, encoding="utf-8") as f:
        rows = list(csv.DictReader(f, delimiter="\t"))
    groups, gain, eq = {}, {}, {}
    for r in rows:
        groups.setdefault((r["case"], r["scale"], r["sub"]), []).append(r)
    for (case, scale, sub), rs in groups.items():
        rs.sort(key=lambda r: int(r["quality"]))
        qs = np.array([int(r["quality"]) for r in rs], float)
        curve = np.maximum.accumulate(np.array([float(r["s2_jpeg"]) for r in rs]))
        for r in rs:
            k = (scale, sub, int(r["quality"]))
            v = float(r["s2_qs6"])
            gain.setdefault(k, []).append(v - float(r["s2_jpeg"]))
            eq.setdefault(k, []).append(100.0 if v > curve[-1] else float(np.interp(v, curve, qs)))
    for title, table, fmt in (("SSIMULACRA2 gain of jpegQS -q 6, median over the pictures", gain, "{:+.1f}"),
                              ("Effective quality with jpegQS -q 6, median over the pictures", eq, "{:.0f}")):
        print(title)
        for sub in ("420", "444"):
            print(f"  {sub}")
            for scale in sorted({k[0] for k in table}, key=lambda s: -int(s)):
                cells = [f"q{q}:" + fmt.format(statistics.median(table[(scale, sub, q)]))
                         for q in QUALITIES if (scale, sub, q) in table]
                print(f"    {scale:>3} %  " + " ".join(cells))
    worse = sum(1 for r in rows if float(r["ba_qs6"]) > float(r["ba_jpeg"]))
    print(f"rows: {len(rows)}; jpegQS -q 6 worse by SSIMULACRA2 in "
          f"{sum(1 for r in rows if float(r['s2_qs6']) < float(r['s2_jpeg']))}, by Butteraugli in {worse}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("set", nargs="?")
    ap.add_argument("work", nargs="?")
    ap.add_argument("out", nargs="?")
    ap.add_argument("--jpegqs")
    ap.add_argument("--libjxl")
    ap.add_argument("--summary")
    ap.add_argument("--axes")
    ap.add_argument("--jpeg2png")
    a = ap.parse_args()
    if a.summary:
        summary(a.summary)
    elif a.axes:
        axes(a.axes, a.jpeg2png)
    else:
        measure(a)


if __name__ == "__main__":
    main()
