"""Reads AntiDupl's decision log (decisions.jsonl in the user folder,
written by the personal build's DecisionLog) and lists the decisions that go
against the pairs' difference, for the settings study (plan 07).

Usage: py -3 decisions_check.py <decisions.jsonl> [--top N] [--tsv out.tsv]
       py -3 decisions_check.py <decisions.jsonl> --keys [--since DATE]

Each pair gets its last decision, with undo and redo applied:
    deleted   a delete (first, second, both, a defect), a hint carried out
              that deletes or replaces one, or a replace (rename first to
              second: the other image takes its name)
    mistake   marked as a mistake: the user keeps both
    linked    one renamed (the user names the other in it), renamed like
              the other, or its group renamed like a neighbour: both kept,
              as related pictures
    moved     one moved next to the other, renamed like it or not, or its
              group moved to a neighbour's folder: both kept
    left      looked at, no action: both kept for now
Printed: counts per decision; the deleted pairs with the highest difference
and the kept pairs (mistake, left) with the lowest, the ones to ask the user
about; and with --tsv every pair with its decision.

--keys lists instead the presses of a hot key that should have made an
action, undo or redo (T26) where the log's next event other than a view is
something else or comes over KEY_ANSWER_SECONDS later: the key, where it went
(the control and window), whether a progress window was open, and what came
next. The action is logged as soon as the hot key is handled, before its
progress window opens, so an answered press is followed at once.
"""
import argparse
import datetime
import json
import sys

DELETING = {"DeleteDefect", "DeleteFirst", "DeleteSecond", "DeleteBoth", "RenameFirstToSecond", "RenameSecondToFirst"}
LINKING = {"RenameFirst", "RenameSecond", "RenameFirstLikeSecond", "RenameSecondLikeFirst", "RenameCurrentGroupAs"}
MOVING = {"MoveFirstToSecond", "MoveSecondToFirst", "MoveAndRenameFirstToSecond", "MoveAndRenameSecondToFirst",
          "MoveCurrentGroupToDirectory"}
HINT_DELETING = {"DeleteFirst", "DeleteSecond", "RenameFirstToSecond", "RenameSecondToFirst"}
# HotKeyOptions.Action names that make a logged action; ShowNeighbours and
# the difftools log nothing.
KEY_ACTIONS = {"CurrentDefectDelete", "CurrentDuplPairDeleteFirst", "CurrentDuplPairDeleteSecond",
               "CurrentDuplPairDeleteBoth", "CurrentDuplPairRenameFirstToSecond",
               "CurrentDuplPairRenameSecondToFirst", "CurrentMistake", "Undo", "Redo"}
KEY_ANSWER_SECONDS = 2


def key(pair):
    # Either order: a sort by one image's property (TResult::OrientFor) can
    # swap a pair's sides between one event and the next.
    a, b = pair["first"]["path"], pair.get("second", {}).get("path", "")
    return (a, b) if not b or a <= b else (b, a)


def decision(action, pair):
    if action in DELETING:
        return "deleted"
    if action == "PerformHint":
        return "deleted" if pair.get("hint") in HINT_DELETING else None
    if action == "Mistake":
        return "mistake"
    if action in LINKING:
        return "linked"
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


def event_time(e):
    # DateTime.ToString("o"): seven fractional digits and the local offset;
    # every event has the same offset, so the local time alone compares.
    return datetime.datetime.fromisoformat(e["time"][:26])


def dropped_keys(events):
    """[(press, next event or None)] for the hot key presses that made no
    action, undo or redo."""
    dropped = []
    for i, e in enumerate(events):
        if e["event"] != "key" or ("hotKey" in e and e["hotKey"] not in KEY_ACTIONS):
            continue
        after = next((f for f in events[i + 1:] if f["event"] != "view"), None)
        if (after is None or after["event"] not in ("action", "undo", "redo")
                or (event_time(after) - event_time(e)).total_seconds() > KEY_ANSWER_SECONDS):
            dropped.append((e, after))
    return dropped


def report_keys(events, since):
    presses = [e for e in events if e["event"] == "key" and e["time"][:10] >= (since or "")]
    dropped = [(e, f) for e, f in dropped_keys(events) if e["time"][:10] >= (since or "")]
    print(f"hot key presses: {len(presses)}, with no action after them: {len(dropped)}")
    for e, f in dropped:
        busy = "progress window open" if e.get("progressWindowOpen") else "no progress window"
        then = "nothing" if f is None else f"{f['event']} {f.get('action', '')} at {f['time'][11:23]}".replace("  ", " ")
        print(f"  {e['time'][:23]}  {e['key']} ({e.get('hotKey', '?')})  to {e.get('to') or '?'} in "
              f"{e.get('window') or '?'}, {busy}{', held down' if e.get('repeat') else ''}; next: {then}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("log")
    ap.add_argument("--top", type=int, default=15)
    ap.add_argument("--tsv")
    ap.add_argument("--keys", action="store_true")
    ap.add_argument("--since")
    a = ap.parse_args()
    events = read_log(a.log)
    if a.keys:
        report_keys(events, a.since)
        return 0
    pairs, decided = replay(events)

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
    kept = sorted((k for k, d in decided.items() if d in ("mistake", "linked", "left")), key=lambda k: pairs[k]["difference"])
    print(f"\nDeleted, highest difference first (top {a.top}):")
    for k in deleted[:a.top]:
        print("  " + line(k))
    print(f"\nKept (mistake, linked or left), lowest difference first (top {a.top}):")
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
