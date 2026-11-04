"""After decision_pairs.py: joins a real run's pairs with the action that
decided each one (the replay's rules, keyboard undo included), the settings
in force and the images' sizes, for the questions to the user and the run's
notes. Writes WORK_DIR\\analysis.tsv and prints the actions per decision, the
image taken away against the one kept, and the search that showed each pair.

Usage: py -3 run_analysis.py <decisions.jsonl> <WORK_DIR>

WORK_DIR is decision_pairs.py's, with its pairs.tsv and scores.tsv.
analysis.tsv's `gone` is the side the action took away: first, second, both.
"""
import collections
import csv
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import decisions_check as dc  # noqa: E402

SCORES = ("ssim-32", "local-colour", "butteraugli-768", "aligned-768")
TAKES_AWAY = {"DeleteFirst": "first", "DeleteSecond": "second", "RenameFirstToSecond": "first", "RenameSecondToFirst": "second"}


def last_actions(events):
    """{pair key: (decision, action, settings, time, pair)}, undo and redo
    applied, as decisions_check's replay decides."""
    state = {}
    done, undone = [], []
    for e in dc.with_keyboard_undo(events):
        if e["event"] in ("search", "start"):
            done.clear()
            undone.clear()
        elif e["event"] == "action":
            applied = []
            for p in e.get("pairs", []):
                d = dc.decision(e["action"], p)
                if d is None:
                    continue
                k = dc.key(p)
                after = (d, e["action"], e.get("settings", {}), e["time"], p)
                applied.append((k, state.get(k), after))
                state[k] = after
            done.append(applied)
            undone.clear()
        elif e["event"] == "undo" and done:
            applied = done.pop()
            for k, before, _ in reversed(applied):
                if before is None:
                    state.pop(k, None)
                else:
                    state[k] = before
            undone.append(applied)
        elif e["event"] == "redo" and undone:
            applied = undone.pop()
            for k, _, after in applied:
                state[k] = after
            done.append(applied)
    return state


def main():
    log, work = sys.argv[1:3]
    state = last_actions(dc.read_log(log))
    with open(os.path.join(work, "scores.tsv"), encoding="utf-8", newline="") as f:
        scores = {r["n"]: r for r in csv.DictReader(f, delimiter="\t")}

    rows = []
    with open(os.path.join(work, "pairs.tsv"), encoding="utf-8", newline="") as f:
        for r in csv.DictReader(f, delimiter="\t"):
            s = state.get(dc.key({"first": {"path": r["first"]}, "second": {"path": r["second"]}}))
            row = {"n": r["n"], "decision": r["decision"], "action": s[1] if s else "",
                   "algorithm": s[2].get("algorithm", "") if s else "", "threshold": s[2].get("threshold", "") if s else "",
                   "time": s[3][:19] if s else "", "logged": r["logged"]}
            for name in SCORES:
                row[name] = scores.get(r["n"], {}).get(name, "")
            if s:
                p = s[4]
                first, second = p["first"], p.get("second", {})
                row["first"], row["second"] = first["path"], second.get("path", "")
                row["first_px"] = first["width"] * first["height"]
                row["second_px"] = second.get("width", 0) * second.get("height", 0)
                row["first_kb"] = first["size"] // 1024
                row["second_kb"] = second.get("size", 0) // 1024
                row["first_fmt"], row["second_fmt"] = first["format"], second.get("format", "")
                row["gone"] = "both" if s[1] == "DeleteBoth" else TAKES_AWAY.get(p.get("hint") if s[1] == "PerformHint" else s[1], "")
            rows.append(row)

    fields = list(dict.fromkeys(k for r in rows for k in r))
    with open(os.path.join(work, "analysis.tsv"), "w", encoding="utf-8", newline="\n") as f:
        w = csv.DictWriter(f, fieldnames=fields, delimiter="\t", extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)

    print("decision x action:")
    for (d, a), n in sorted(collections.Counter((r["decision"], r["action"]) for r in rows).items()):
        print(f"  {d:8} {a or '-':28} {n}")
    print("\none deleted: the image taken away against the one kept")
    sides = collections.Counter()
    for r in rows:
        if r.get("gone") not in ("first", "second"):
            continue
        taken, kept = ("first", "second") if r["gone"] == "first" else ("second", "first")
        px = r[taken + "_px"] - r[kept + "_px"]
        kb = r[taken + "_kb"] - r[kept + "_kb"]
        sides[("fewer pixels" if px < 0 else "more pixels" if px > 0 else "same pixels",
               "smaller file" if kb < 0 else "larger file" if kb > 0 else "same size")] += 1
    for c, n in sides.most_common():
        print(f"  {c[0]:13} {c[1]:13} {n}")
    print("\nsearch that showed the pair (algorithm, threshold) per decision:")
    for (d, a, t), n in sorted(collections.Counter((r["decision"], r["algorithm"], r["threshold"]) for r in rows).items()):
        print(f"  {d:8} {a:12} {t:>6} {n}")


if __name__ == "__main__":
    main()
