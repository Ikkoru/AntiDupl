"""Reads AntiDupl's decision log (decisions.jsonl in the user folder,
written by the personal build's DecisionLog) and lists the decisions that go
against the pairs' difference, for the settings study (plan 07).

Usage: py -3 decisions_check.py <decisions.jsonl> [--top N] [--tsv out.tsv]

Each pair gets its last decision, with undo and redo applied:
    deleted   a delete (first, second, both), a hint carried out that
              deletes or replaces one, or a rename of one to the other
    mistake   marked as a mistake: the user keeps both
    moved     one moved next to the other: both kept
    left      looked at, no action: both kept for now
Printed: counts per decision; the deleted pairs with the highest difference
and the kept pairs (mistake, left) with the lowest, the ones to ask the user
about; and with --tsv every pair with its decision.
"""
import argparse
import json
import sys

DELETING = {"DeleteFirst", "DeleteSecond", "DeleteBoth", "RenameFirstToSecond", "RenameSecondToFirst",
            "MoveAndRenameFirstToSecond", "MoveAndRenameSecondToFirst"}
MOVING = {"MoveFirstToSecond", "MoveSecondToFirst"}
HINT_DELETING = {"DeleteFirst", "DeleteSecond", "RenameFirstToSecond", "RenameSecondToFirst"}


def key(pair):
    return (pair["first"]["path"], pair.get("second", {}).get("path", ""))


def decision(action, pair):
    if action in DELETING:
        return "deleted"
    if action == "PerformHint":
        return "deleted" if pair.get("hint") in HINT_DELETING else None
    if action == "Mistake":
        return "mistake"
    if action in MOVING:
        return "moved"
    return None


def read_log(path):
    return [json.loads(line) for line in open(path, encoding="utf-8") if line.strip()]


def replay(events):
    """Each pair's info as last seen and its last decision, undo and redo
    applied: ({key: pair}, {key: decision})."""
    pairs = {}        # key -> pair info as last seen
    decided = {}      # key -> decision
    done, undone = [], []   # stacks of applied actions: [(key, previous decision)]
    for e in events:
        if e["event"] == "view":
            k = key(e)
            pairs.setdefault(k, e)
            decided.setdefault(k, "left")
        elif e["event"] == "action":
            applied = []
            for p in e.get("pairs", []):
                d = decision(e["action"], p)
                if d is None:
                    continue
                k = key(p)
                pairs[k] = p
                applied.append((k, decided.get(k, "left"), d))
                decided[k] = d
            done.append(applied)
            undone.clear()
        elif e["event"] == "undo" and done:
            applied = done.pop()
            for k, before, _ in applied:
                decided[k] = before
            undone.append(applied)
        elif e["event"] == "redo" and undone:
            applied = undone.pop()
            for k, _, after in applied:
                decided[k] = after
            done.append(applied)
    return pairs, decided


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("log")
    ap.add_argument("--top", type=int, default=15)
    ap.add_argument("--tsv")
    a = ap.parse_args()
    pairs, decided = replay(read_log(a.log))

    counts = {}
    for d in decided.values():
        counts[d] = counts.get(d, 0) + 1
    print("pairs: " + ", ".join(f"{d} {n}" for d, n in sorted(counts.items())))

    def line(k):
        p = pairs[k]
        f, s = p["first"], p.get("second", {})
        return (f"{p['difference']:.6f}  {decided[k]:<8} {f['path']}  |  {s.get('path', '')}  "
                f"({f['format']} {f['width']}x{f['height']} {f['size']} B vs {s.get('format', '')} "
                f"{s.get('width', '')}x{s.get('height', '')} {s.get('size', '')} B)")

    deleted = sorted((k for k, d in decided.items() if d == "deleted"), key=lambda k: -pairs[k]["difference"])
    kept = sorted((k for k, d in decided.items() if d in ("mistake", "left")), key=lambda k: pairs[k]["difference"])
    print(f"\nDeleted, highest difference first (top {a.top}):")
    for k in deleted[:a.top]:
        print("  " + line(k))
    print(f"\nKept (mistake or left), lowest difference first (top {a.top}):")
    for k in kept[:a.top]:
        print("  " + line(k))
    if a.tsv:
        with open(a.tsv, "w", encoding="utf-8", newline="\n") as f:
            f.write("difference\tdecision\tfirst\tsecond\n")
            for k in sorted(decided, key=lambda k: pairs[k]["difference"]):
                f.write(f"{pairs[k]['difference']}\t{decided[k]}\t{k[0]}\t{k[1]}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
