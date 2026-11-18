"""Copies the images the decision log's pairs lost to the Recycle Bin into a
lasting folder, before the bin is emptied: for the settings study's real
runs (decision_pairs.py --rescued reads them back). Only copies; scores
nothing, so it is quick enough to run often (a scheduled task).

Usage:
    py -3 recycle_rescue.py LOG STORE [--since DATE]

LOG    the decision log of the user's everyday AntiDupl (decisions.jsonl)
STORE  the lasting folder: <YYYY-MM>\\<n> <name> per image, and index.tsv,
       one line per image: its logged path, size and modification time,
       the stored file (relative to STORE), where it was found, and when
--since  only pairs first seen on or after this date (YYYY-MM-DD)
--unneeded  prints the stored copies no useful pair needs (to recycle);
       a later run drops the index lines of copies no longer there

Only images in a pair that is not pixel-identical are copied (useful):
a pair every algorithm gives 0.00 teaches the study nothing.

An image counts as lost when it is no longer at its path, where a rename or
a replace took it, or at the other image's (decision_pairs.locate); it is
copied only when found in the Recycle Bin, by path or by size and date. An
image already in the index is skipped, so a run copies only what is new.
Reads the archive and the bins; writes only into STORE.
"""
import argparse
import csv
import datetime
import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import decision_pairs as dp  # noqa: E402
import decisions_check as dc  # noqa: E402

FIELDS = ["path", "size", "modified", "stored", "found", "rescued"]
IDENTICAL_MAX = 0.00001


def identity(info):
    return (info["path"].lower(), info["size"], info.get("modified") or "")


def read_index(store):
    """{identity: row} of the images already stored."""
    path = os.path.join(store, "index.tsv")
    if not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8", newline="") as f:
        return {(r["path"].lower(), int(r["size"]), r["modified"]): r for r in csv.DictReader(f, delimiter="\t")}


def stored(store, info, index=None):
    """The stored copy of a logged image, or None."""
    row = (index if index is not None else read_index(store)).get(identity(info))
    return os.path.join(store, row["stored"]) if row else None


def useful(p):
    """Whether a pair can teach the study anything: not pixel-identical
    (the GUI's 0.00, DifferenceFormat.IDENTICAL_MAX), which every
    algorithm already gets right."""
    return p.get("difference") is not None and float(p["difference"]) >= IDENTICAL_MAX


def write_index(path, rows):
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS, delimiter="\t", lineterminator="\n")
        w.writeheader()
        w.writerows(rows)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("log")
    ap.add_argument("store")
    ap.add_argument("--since")
    ap.add_argument("--unneeded", action="store_true")
    a = ap.parse_args()

    events = dc.read_log(a.log)
    first_seen = {}
    for e in events:
        for p in dc.event_pairs(e):
            if "second" in p:
                first_seen.setdefault(dc.key(p), e["time"])
    pairs, _ = dc.replay(events)
    moved = dp.renames(events)
    # The images worth keeping: those in at least one useful pair.
    wanted = {}
    for k, p in pairs.items():
        if not p.get("second") or k not in first_seen or (a.since and first_seen[k][:10] < a.since):
            continue
        for info, other in ((p["first"], p["second"]["path"]), (p["second"], p["first"]["path"])):
            if useful(p) or identity(info) not in wanted:
                wanted[identity(info)] = (info, other, useful(p) or wanted.get(identity(info), (0, 0, False))[2])
    os.makedirs(a.store, exist_ok=True)
    index = read_index(a.store)
    path = os.path.join(a.store, "index.tsv")
    # Rows whose copy was deleted (recycled as unneeded) go.
    present = [r for r in index.values() if os.path.exists(os.path.join(a.store, r["stored"]))]
    if len(present) != len(index) or not os.path.exists(path):
        write_index(path, present)
        index = read_index(a.store)
    if a.unneeded:
        for ident, r in index.items():
            if not (ident in wanted and wanted[ident][2]):
                print(os.path.join(a.store, r["stored"]))
        return
    numbers = [int(r["stored"].split("\\")[-1].split("/")[-1].split(" ", 1)[0]) for r in index.values()]
    new_rows, missing, skipped = [], 0, 0
    for ident, (info, other, worth) in wanted.items():
        if ident in index:
            continue
        if not worth:
            skipped += 1
            continue
        src, where = dp.locate(info, other, moved)
        if src is None:
            missing += 1
            continue
        if not where.startswith("recycle bin"):
            continue
        month = datetime.date.today().strftime("%Y-%m")
        n = max(numbers, default=0) + len(new_rows) + 1
        rel = os.path.join(month, f"{n} {os.path.basename(info['path'])}")
        os.makedirs(os.path.join(a.store, month), exist_ok=True)
        shutil.copy2(src, os.path.join(a.store, rel))
        row = {"path": info["path"], "size": info["size"], "modified": info.get("modified") or "",
               "stored": rel, "found": where, "rescued": datetime.datetime.now().isoformat(timespec="seconds")}
        # Written after each copy: a run cut short leaves every copy it
        # made in the index.
        with open(path, "a", encoding="utf-8", newline="") as f:
            csv.DictWriter(f, fieldnames=FIELDS, delimiter="\t", lineterminator="\n").writerow(row)
        new_rows.append(row)
    print(f"rescued {len(new_rows)}, already stored {len(index)}, only in pixel-identical pairs {skipped}, "
          f"lost (not in a bin) {missing}")


if __name__ == "__main__":
    main()
