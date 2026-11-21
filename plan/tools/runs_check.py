"""Checks real runs saved by decision_pairs.py --keep against what a run may
keep: a README.md that says what the run is and what reads it, and in
pairs\\ only pairs a later study can use. Prints each problem; exit 1 if any.

    py -3 runs_check.py <run folder>...

A pair folder holds <n>a.<ext> and <n>b.<ext> of a pair in pairs.tsv, and
any other file only where the run's README names it with its use. Not
kept: a pixel-identical pair (it scores 0 under every setting, and the
highlight skips it), a pair with one image (it can't be scored). Every
file beside pairs\\ is named in the README too. Images PIL can't decode
(HEIC) are compared by bytes only.
"""
import csv
import os
import re
import sys

from PIL import Image, ImageFile

ImageFile.LOAD_TRUNCATED_IMAGES = True
Image.MAX_IMAGE_PIXELS = None


def same_pixels(a, b):
    if open(a, "rb").read() == open(b, "rb").read():
        return True
    try:
        ia, ib = Image.open(a), Image.open(b)
        if ia.size != ib.size:
            return False
        return ia.convert("RGBA").tobytes() == ib.convert("RGBA").tobytes()
    except Exception:
        return False


def check(run):
    problems = []
    readme_path = os.path.join(run, "README.md")
    if not os.path.isfile(readme_path):
        problems.append("no README.md")
        readme = ""
    else:
        readme = open(readme_path, encoding="utf-8").read()
    for name in os.listdir(run):
        if name not in ("README.md", "pairs") and name not in readme:
            problems.append(f"{name}: not named in README.md")
    pairs_tsv = os.path.join(run, "pairs.tsv")
    known = set()
    if os.path.isfile(pairs_tsv):
        known = {r["n"] for r in csv.DictReader(open(pairs_tsv, encoding="utf-8"), delimiter="\t")}
    pairs = os.path.join(run, "pairs")
    if not os.path.isdir(pairs):
        return problems
    for n in sorted(os.listdir(pairs), key=lambda s: (len(s), s)):
        folder = os.path.join(pairs, n)
        if n not in known:
            problems.append(f"pairs\\{n}: not in pairs.tsv")
        files = os.listdir(folder)
        sides = {m.group(1): f for f in files if (m := re.fullmatch(re.escape(n) + r"([ab])\.[^.]+", f))}
        for f in files:
            if f not in sides.values() and f not in readme:
                problems.append(f"pairs\\{n}\\{f}: not a side of the pair, not named in README.md")
        if len(sides) != 2:
            problems.append(f"pairs\\{n}: {len(sides)} image(s), a pair needs both")
        elif same_pixels(os.path.join(folder, sides["a"]), os.path.join(folder, sides["b"])):
            problems.append(f"pairs\\{n}: pixel-identical")
    return problems


def main():
    bad = 0
    for run in sys.argv[1:]:
        problems = check(run)
        print(f"{run}: {'ok' if not problems else str(len(problems)) + ' problem(s)'}")
        for p in problems:
            print("  " + p)
        bad += len(problems)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
