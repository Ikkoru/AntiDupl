"""The WebP trace in the transform domain, a first test (plan 07, "Which
copy is worse"): do a decoded WebP's 4x4 transform coefficients still lie
on lattices? VP8 quantises each 4x4 block's residual after prediction
with one AC step for all positions of the luma.

For a few of the set's never-WebP pictures per illustration, the samples
of webp_trace.py; per sample: VP8's luma (BT.601 limited range, as
libwebp converts), 4x4 blocks, unclipped ones only, orthonormal DCT; per
AC position the lattice score, cos(2 pi D / s) averaged over the
coefficients |D| >= s / 2 (at least 200 of them), for each step s from 2
to 80 in steps of 0.5; the score of a sample is the mean of its three
best positions' scores, its step the median of their steps. At the
sample's own grid (phase 0) and at the best of the 16 phases.

--analyze: one illustration left out at a time, the trace counts when
the score is over the highest never-WebP score of the other
illustrations, and the quality is that of the Pillow method-4 samples of
the other illustrations whose median step is nearest (in log).

Usage: py -3 webp_lattice.py <set> <out.csv> [--per-case N] [--workers N]
       py -3 webp_lattice.py --analyze <out.csv>
"""
import argparse
import collections
import csv
import os
import sys
import tempfile
from concurrent.futures import ProcessPoolExecutor

import numpy as np
from PIL import Image

STEPS = np.arange(2, 80.5, 0.5)
POSITIONS = [(u, v) for u in range(4) for v in range(4) if (u, v) != (0, 0)]


def lattice(im, phases):
    """(score, step, phase) at the best of the given (dy, dx) phases."""
    from scipy import fft
    y = 16 + np.asarray(im, dtype=np.float64) @ np.array([0.2569, 0.5044, 0.0980])
    best = None
    for dy, dx in phases:
        z = y[dy:, dx:]
        n = z.shape[0] // 4 * 4, z.shape[1] // 4 * 4
        blocks = z[:n[0], :n[1]].reshape(n[0] // 4, 4, n[1] // 4, 4).transpose(0, 2, 1, 3).reshape(-1, 4, 4)
        keep = (blocks.min(axis=(1, 2)) > 18) & (blocks.max(axis=(1, 2)) < 233)
        c = fft.dctn(blocks[keep], axes=(1, 2), norm="ortho")
        per = []
        for u, v in POSITIONS:
            d = c[:, u, v]
            top = (0.0, 0.0)
            for s in STEPS:
                sel = d[np.abs(d) >= s / 2]
                if len(sel) < 200:
                    break
                score = float(np.cos(2 * np.pi * sel / s).mean())
                if score > top[0]:
                    top = (score, float(s))
            per.append(top)
        per.sort(reverse=True)
        score, step = float(np.mean([p[0] for p in per[:3]])), float(np.median([p[1] for p in per[:3]]))
        if best is None or score > best[0]:
            best = (score, step, f"{dx},{dy}")
    return best


def job(img):
    import webp_trace as wt
    im = Image.open(img["path"]).convert("RGB")
    w, h = im.size
    side = min(wt.SIDE, min(w, h) // 16 * 16)
    x0, y0 = (w - side) // 2 // 16 * 16, (h - side) // 2 // 16 * 16
    im = im.crop((x0, y0, x0 + side, y0 + side))
    with tempfile.TemporaryDirectory() as scratch:
        return [[img["case"], img["stem"], family, encoder, q, detail,
                 *lattice(s, [(0, 0)]), *lattice(s, [(dy, dx) for dy in range(4) for dx in range(4)])]
                for family, encoder, q, detail, s in wt.samples(im, scratch)]


def band(q):
    return "q20-45" if q < 50 else "q50-70" if q < 75 else "q75-85" if q < 90 else "q90-95"


def analyze(path):
    rows = list(csv.DictReader(open(path, encoding="utf-8")))
    for r in rows:
        r["q"] = int(r["webp_q"]) if r["webp_q"] else None
        r["group"] = (("never", r["sample"]) if r["family"] == "never"
                      else (f"webp {r['encoder']}", band(r["q"])) if r["family"] == "webp" else ("chain", r["sample"]))
    cases = sorted({r["case"] for r in rows})
    for tag, label in (("0", "the sample's own grid"), ("16", "the best of 16 phases")):
        found, close, total, false = collections.Counter(), collections.Counter(), collections.Counter(), []
        for test in cases:
            train = [r for r in rows if r["case"] != test]
            t = max(float(r["score" + tag]) for r in train if r["family"] == "never")
            steps = collections.defaultdict(list)
            for r in train:
                if r["family"] == "webp" and r["encoder"] == "pillow-m4":
                    steps[r["q"]].append(float(r["step" + tag]))
            table = {q: float(np.median(v)) for q, v in steps.items()}
            for r in rows:
                if r["case"] != test:
                    continue
                total[r["group"]] += 1
                hit = float(r["score" + tag]) > t
                found[r["group"]] += hit
                if hit and r["q"] is not None:
                    s = max(float(r["step" + tag]), 0.5)
                    q_hat = min(table, key=lambda q: abs(np.log(table[q]) - np.log(s)))
                    close[r["group"]] += abs(q_hat - r["q"]) <= 5
                if hit and r["family"] == "never":
                    false.append(r)
        print(f"\n{label}: never-WebP samples with a trace {len(false)} of {sum(n for g, n in total.items() if g[0] == 'never')}")
        for g in sorted(total):
            if g[0] != "never":
                print(f"  {g[0] + ' ' + g[1]:44s} {total[g]:4d}  found {100 * found[g] / total[g]:3.0f} %, "
                      f"with the quality within 5 {100 * close[g] / total[g]:3.0f} %")
        top = collections.defaultdict(float)
        for r in rows:
            if r["family"] == "never":
                top[r["sample"]] = max(top[r["sample"]], float(r["score" + tag]))
        print("  highest never-WebP score per kind: " + ", ".join(f"{k} {v:.2f}" for k, v in sorted(top.items())))
        m4 = collections.defaultdict(list)
        for r in rows:
            if r["family"] == "webp" and r["encoder"] == "pillow-m4":
                m4[r["q"]].append((float(r["score" + tag]), float(r["step" + tag])))
        print("  Pillow m4, lowest score / median step per quality: " + ", ".join(
            f"q{q} {min(a for a, _ in v):.2f}/{np.median([b for _, b in v]):.1f}" for q, v in sorted(m4.items())))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("set", nargs="?")
    ap.add_argument("out")
    ap.add_argument("--per-case", type=int, default=3)
    ap.add_argument("--workers", type=int, default=os.cpu_count())
    ap.add_argument("--analyze", action="store_true")
    a = ap.parse_args()
    if a.analyze:
        analyze(a.out)
        return 0
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import settings_study as ss
    images = ss.load_set(a.set)
    sources = []
    for case in sorted({i["case"] for i in images}):
        pool = [i for i in images if i["case"] == case and i["kind"] in ("original", "variant", "step")]
        sources += pool[::max(1, len(pool) // a.per_case)][:a.per_case]
    with open(a.out, "w", encoding="utf-8", newline="") as f:
        out = csv.writer(f)
        out.writerow(["case", "source", "family", "encoder", "webp_q", "sample",
                      "score0", "step0", "phase0", "score16", "step16", "phase16"])
        with ProcessPoolExecutor(a.workers) as pool:
            for n, rows in enumerate(pool.map(job, sources), 1):
                out.writerows(rows)
                f.flush()
                print(f"{n}/{len(sources)}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
