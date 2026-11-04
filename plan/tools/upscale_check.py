"""On a real run's saved pairs: which of the copies of different sizes the
upscale test (study_metrics.line_detail) flags, against what the user kept.

Usage: py -3 upscale_check.py ANALYSIS_TSV SCORES_TSV PAIRS_DIR [--limit S]

ANALYSIS_TSV  run_analysis.py's table
SCORES_TSV    a table with `n` and the pair's aligned score in `aligned` or
              `aligned-768`, for the pairs that show the same picture
PAIRS_DIR     one folder per pair, named by its number, with its two images
--limit       the aligned score a pair counts as a copy up to (default 15)

Prints per pair of at least 1.15 times the pixels: its number, the decision,
what the user kept, the scale, line_detail and whether it is flagged; then how
many of each. The same two images under several pair numbers count once.
A pair needs OpenCV (STUDY_PYLIB) to be cut to what the two share.
"""
import argparse
import csv
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import study_metrics as sm  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("analysis")
    ap.add_argument("scores")
    ap.add_argument("pairs")
    ap.add_argument("--limit", type=float, default=15)
    a = ap.parse_args()
    with open(a.scores, encoding="utf-8", newline="") as f:
        scores = {r["n"]: r.get("aligned") or r.get("aligned-768") or "" for r in csv.DictReader(f, delimiter="\t")}
    with open(a.analysis, encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f, delimiter="\t"))

    seen, tally = set(), {}
    print("pair  decision  kept  scale  line detail  flagged")
    for r in sorted(rows, key=lambda r: int(r["n"])):
        score = scores.get(r["n"], "")
        first, second = int(r.get("first_px") or 0), int(r.get("second_px") or 0)
        folder = os.path.join(a.pairs, r["n"])
        if not score or float(score) > a.limit or min(first, second) == 0 or not os.path.isdir(folder):
            continue
        if max(first, second) / min(first, second) < 1.15 or frozenset((r["first"], r["second"])) in seen:
            continue
        names = sorted(os.listdir(folder))
        if len(names) != 2 or r.get("gone") == "both":
            continue
        seen.add(frozenset((r["first"], r["second"])))
        small, large = (names[0], names[1]) if first < second else (names[1], names[0])
        value = sm.line_detail(os.path.join(folder, small), os.path.join(folder, large))
        kept = "both" if not r.get("gone") else "larger" if (r["gone"] == "second") == (first > second) else "smaller"
        flagged = value < sm.UPSCALED_LINE_DETAIL
        print(f'{r["n"]:>5}  {r["decision"]:8}  {kept:7}  {(max(first, second) / min(first, second)) ** 0.5:5.2f}  {value:5.2f}  {"upscale" if flagged else ""}', flush=True)
        tally[kept, flagged] = tally.get((kept, flagged), 0) + 1
    print()
    for (kept, flagged), n in sorted(tally.items()):
        print(f'kept {kept}: {n} {"flagged" if flagged else "not flagged"}')


if __name__ == "__main__":
    main()
