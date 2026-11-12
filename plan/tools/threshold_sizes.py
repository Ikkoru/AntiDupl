"""What Butteraugli's two thresholds should be at each working size, from real
runs: the pairs a run's scores put up to 50 at 768 px, scored at every working
size, plain and aligned. For the values in CoreOptionsForm
(THRESHOLD_DIFFERENCE_DEFAULT_BUTTERAUGLI and _WIDE_BUTTERAUGLI).

Usage:
    py -3 threshold_sizes.py WORK_DIR --dll BIN_RELEASE [--skip TEXT]...
                             [--anchors 8.5,15] RUN_DIR...

WORK_DIR  a scratch folder: pairs\\<id>\\ gets the two images, scores.tsv the
          scores; a second run reuses the copies
--dll     a build with both algorithms (the personal branch's bin\\Release)
--skip    leaves out pairs with this text in a path: folders of copies the
          user keeps on purpose, whose "mistakes" aren't versions
--anchors the two thresholds at 768 px (the default and the second one) to
          find the matching ones of at every size for (default 8.5,15)
RUN_DIR  a run saved by decision_pairs.py --keep: its pairs.tsv, its
          scores.tsv, and aligned-scores.tsv where there is one, with the
          columns n, decision, plain, aligned. A pair comes from the run's
          pairs folder, or else from the two files pairs.tsv names, which
          are read and copied, nothing else

Prints per size and threshold the pairs the user kept (marked as mistakes) and
acted on (deleted, linked, moved), then the threshold at each size that lets
through about the same pairs as the anchors at 768 px. Images smaller than a
working size aren't enlarged, so at the larger sizes small images score alike.
"""
import argparse
import csv
import glob
import os
import re
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SIZES = (384, 512, 768, 1024)
# CoreOptionsForm.ThresholdValues, past 0
STEPS = [i * 0.5 for i in range(1, 21)] + list(range(11, 21)) + list(range(25, 51, 5))
LINE = re.compile(r"^([0-9.]+)  shows \S+  (.+?) \| (.+?)(?:  transform \d+)?$")


def read(path):
    with open(path, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f, delimiter="\t"))


def run_pairs(run):
    """(n, decision) of the pairs scored up to 50 at 768 px, plain or aligned."""
    aligned = os.path.join(run, "aligned-scores.tsv")
    if os.path.exists(aligned):
        return [(r["n"], r["decision"]) for r in read(aligned) if r["plain"] or r["aligned"]]
    return [(r["n"], r["decision"]) for r in read(os.path.join(run, "scores.tsv"))
            if any(r.get(c) and float(r[c]) <= 50 for c in ("butteraugli-768", "aligned-768"))]


def collect(runs, pair_dir, skip):
    """Copies each run's pairs to <pair_dir>\\<id>; returns {id: decision}.
    A pair's id is the run's place in the list, then its number."""
    found, missing = {}, 0
    for index, run in enumerate(runs, 1):
        named = {r["n"]: r for r in read(os.path.join(run, "pairs.tsv"))}
        for n, decision in run_pairs(run):
            if any(text in named[n]["first"] + named[n]["second"] for text in skip):
                continue
            pair = f"{index}{int(n):05}"
            folder = os.path.join(pair_dir, pair)
            if not os.path.isdir(folder):
                saved = sorted(glob.glob(glob.escape(os.path.join(run, "pairs", n)) + os.sep + "*"))
                sources = saved if len(saved) == 2 else [named[n]["first"], named[n]["second"]]
                if not all(os.path.exists(s) for s in sources):
                    missing += 1
                    continue
                os.makedirs(folder)
                for side, src in zip("ab", sources):
                    shutil.copy2(src, os.path.join(folder, pair + side + os.path.splitext(src)[1]))
            found[pair] = decision
    print(f"{len(found)} pairs, {missing} with an image gone")
    return found


def score(work, pair_dir, dll, pairs):
    """{column: {id: score}}, one search per algorithm and size."""
    scores = {}
    for algorithm, name in ((4, "plain"), (5, "aligned")):
        for size in SIZES:
            column = f"{name}-{size}"
            user = os.path.join(work, "user-" + column)
            os.makedirs(user, exist_ok=True)
            out = subprocess.run([sys.executable, os.path.join(HERE, "core_search.py"), dll, user, pair_dir, "--any-ratio",
                                  "--algorithm", str(algorithm), "--size", "128", "--threshold", "50",
                                  "--butteraugli-size", str(size)],
                                 capture_output=True, text=True, encoding="ascii", errors="replace").stdout
            values = scores[column] = {}
            for line in out.splitlines():
                m = LINE.match(line)
                if m:
                    a, b = (os.path.splitext(x)[0] for x in (m.group(2), m.group(3)))
                    if a[:-1] == b[:-1] and a[:-1] in pairs and {a[-1], b[-1]} == {"a", "b"}:
                        values[a[:-1]] = min(values.get(a[:-1], float("inf")), float(m.group(1)))
            print(f"{column}: {len(values)} of {len(pairs)}", flush=True)
    return scores


def counts(values, pairs, threshold):
    """The pairs up to a threshold: (kept, acted on)."""
    kept = acted = 0
    for pair, value in values.items():
        if value <= threshold:
            if pairs[pair] == "mistake":
                kept += 1
            elif pairs[pair] != "left":
                acted += 1
    return kept, acted


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("work")
    ap.add_argument("--dll", required=True)
    ap.add_argument("--skip", action="append", default=[])
    ap.add_argument("--anchors", default="8.5,15")
    ap.add_argument("runs", nargs="+")
    a = ap.parse_args()
    anchors = [float(x) for x in a.anchors.split(",")]

    pair_dir = os.path.join(a.work, "pairs")
    os.makedirs(pair_dir, exist_ok=True)
    pairs = collect(a.runs, pair_dir, a.skip)
    scores = score(a.work, pair_dir, a.dll, pairs)
    columns = list(scores)
    with open(os.path.join(a.work, "scores.tsv"), "w", encoding="utf-8", newline="\n") as f:
        f.write("id\tdecision\t" + "\t".join(columns) + "\n")
        for pair, decision in pairs.items():
            f.write(f"{pair}\t{decision}\t" + "\t".join(str(scores[c].get(pair, "")) for c in columns) + "\n")

    for name in ("plain", "aligned"):
        print(f"\n{name}: kept and acted on, up to each threshold")
        print("  threshold " + "".join(f"{size:>14}" for size in SIZES))
        for step in STEPS:
            cells = (counts(scores[f"{name}-{size}"], pairs, step) for size in SIZES)
            print(f"  {step:>9} " + "".join(f"{k:>7} {x:>6}" for k, x in cells))
        for anchor in anchors:
            base = counts(scores[f"{name}-768"], pairs, anchor)
            print(f"  as {anchor} at 768 px {base}:")
            for size in SIZES:
                values = scores[f"{name}-{size}"]
                best = min(STEPS, key=lambda t: (abs(counts(values, pairs, t)[0] - base[0]) +
                                                 abs(counts(values, pairs, t)[1] - base[1]), t))
                print(f"    {size}: {best} {counts(values, pairs, best)}")


if __name__ == "__main__":
    main()
