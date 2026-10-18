"""Join core_search.py runs on the settings study's cases with the study's
pair classes, to choose an algorithm's threshold.

Usage:
    py -3 core_calibration.py SET PAIRS_CSV RUN_DIR [--thresholds 1,2,4]
                              [--compare COLUMN]

SET        the study's sample set (Research\\set), for each image's kind
PAIRS_CSV  the study's pairs.csv: the class of every pair within a case
RUN_DIR    one core_search.py output per case, named <case>.txt: one search
           of the case's folder each (file names repeat across cases), with a
           threshold high enough to report every pair worth judging
--thresholds  the thresholds to count each side of (default 1 to 10 in 0.5)
--compare  a pairs.csv column to rank-correlate with the core's values over
           the pairs the core found (say butteraugli-512, libjxl's)
--exclude  file names (comma-separated) to leave out of every case, such as
           a format the build can't decode

A pair the core did not report (filtered out, or over the run's threshold)
counts as not found. Prints, per class, the pairs found and their values;
the largest value of a plain copy (compressed, resized, web copy, upscaled),
with and without the 12-25 % copies, and the versions at or below it; and
for each threshold the versions at or below it and the plain copies above.
"""
import argparse
import csv
import math
import os
import re
import statistics
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import settings_study as ss  # noqa: E402

LINE = re.compile(r"^([0-9.]+)  shows \S+  (.+?) \| (.+?)(?:  transform \d+)?$")


def read_runs(run_dir, cases):
    found = {}
    for case in cases:
        path = os.path.join(run_dir, f"{case}.txt")
        if not os.path.exists(path):
            sys.exit(f"no run for case {case}: {path}")
        for line in open(path, encoding="ascii", errors="replace"):
            m = LINE.match(line.rstrip("\n"))
            if not m or m.group(2) == m.group(3):
                continue
            key = (case, frozenset((m.group(2), m.group(3))))
            found[key] = min(found.get(key, math.inf), float(m.group(1)))
    return found


def ranks(values):
    order = sorted(range(len(values)), key=lambda i: values[i])
    r = [0.0] * len(values)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and values[order[j + 1]] == values[order[i]]:
            j += 1
        for k in range(i, j + 1):
            r[order[k]] = (i + j) / 2
        i = j + 1
    return r


def spearman(x, y):
    rx, ry = ranks(x), ranks(y)
    mx, my = statistics.fmean(rx), statistics.fmean(ry)
    num = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    den = math.sqrt(sum((a - mx) ** 2 for a in rx) * sum((b - my) ** 2 for b in ry))
    return num / den if den else float("nan")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("set")
    ap.add_argument("pairs_csv")
    ap.add_argument("run_dir")
    ap.add_argument("--thresholds", default=",".join(str(t / 2) for t in range(2, 21)))
    ap.add_argument("--compare")
    ap.add_argument("--exclude", default="")
    a = ap.parse_args()

    images = {(i["case"], i["file"]): i for i in ss.load_set(a.set)}
    excluded = set(filter(None, a.exclude.split(",")))
    rows = [r for r in csv.DictReader(open(a.pairs_csv, encoding="utf-8"))
            if r["case_a"] == r["case_b"] and r["a"] not in excluded and r["b"] not in excluded]
    found = read_runs(a.run_dir, sorted({r["case_a"] for r in rows}))
    for r in rows:
        r["value"] = found.get((r["case_a"], frozenset((r["a"], r["b"]))), math.inf)

    def plain(r, small=True):
        ia, ib = images[(r["case_a"], r["a"])], images[(r["case_b"], r["b"])]
        if r["class"] != "copy" or not all(ss.kind_of(i) in ss.PLAIN for i in (ia, ib)):
            return False
        return small or not any(i["stem"].startswith(("scale-12", "scale-25")) for i in (ia, ib))

    print(f"{'class':16} {'pairs':>6} {'found':>6} {'median':>8} {'max':>8}")
    for cls in sorted({r["class"] for r in rows}):
        sel = [r["value"] for r in rows if r["class"] == cls]
        fin = [v for v in sel if v < math.inf]
        med = f"{statistics.median(fin):8.3f}" if fin else f"{'-':>8}"
        top = f"{max(fin):8.3f}" if fin else f"{'-':>8}"
        print(f"{cls:16} {len(sel):6} {len(fin):6} {med} {top}")

    versions = [r for r in rows if r["class"] in ss.VERSION_CLASSES]
    print()
    for small in (True, False):
        copies = [r for r in rows if plain(r, small)]
        last = max(r["value"] for r in copies)
        missed = sum(1 for r in copies if r["value"] == math.inf)
        below = sum(1 for r in versions if r["value"] <= last)
        print(f"plain copies {'with' if small else 'without'} the 12-25 % ones: {len(copies)}, "
              f"not found {missed}, last {last:.3f}; versions at or below it {below} of {len(versions)}")

    print("\nthe largest plain copies and the closest versions:")
    worst = sorted((r for r in rows if plain(r)), key=lambda r: -r["value"])[:5]
    closest = sorted(versions, key=lambda r: r["value"])[:5]
    for r in worst + closest:
        print(f"  {r['value']:8.3f}  {r['class']:14} {r['case_a']}: {r['a']} | {r['b']}")

    print()
    print(f"{'threshold':>9} {'versions <=':>12} {'plain copies >':>15} {'(without 12-25 %)':>18}")
    for t in (float(x) for x in a.thresholds.split(",")):
        v = sum(1 for r in versions if r["value"] <= t)
        c = sum(1 for r in rows if plain(r) and r["value"] > t)
        c2 = sum(1 for r in rows if plain(r, False) and r["value"] > t)
        print(f"{t:9.2f} {v:12} {c:15} {c2:18}")

    if a.compare:
        pairs = [(r["value"], float(r[a.compare])) for r in rows if r["value"] < math.inf and r[a.compare]]
        print(f"\nrank correlation with {a.compare} over {len(pairs)} found pairs: "
              f"{spearman([p[0] for p in pairs], [p[1] for p in pairs]):.3f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
