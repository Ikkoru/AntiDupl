"""Copies the pairs of a decision log (decisions.jsonl, T17) out of the
archive, or out of the Recycle Bin for a deleted image, and scores each pair
with every algorithm through a build's core, for the settings study
(plan 07): which algorithm would have shown each pair the user decided on.

Usage:
    py -3 decision_pairs.py LOG WORK_DIR --dll BIN_RELEASE [--since DATE] [--keep DIR] [--rescued STORE]

LOG       the decision log of the user's everyday AntiDupl
WORK_DIR  a scratch folder: pairs\\<n>\\ gets the two images as <n>a and
          <n>b, pairs.tsv the pairs, scores.tsv every algorithm's value,
          report.txt what is printed
--dll     a build with every algorithm (the personal branch's bin\\Release)
--since   only pairs first seen on or after this date (YYYY-MM-DD)
--keep    a lasting folder for the run: pairs.tsv, scores.tsv, the report,
          and the copies of the pairs a later run can't copy again from the
          archive (any pair with an image found in the Recycle Bin, which
          it leaves when emptied: the deleted ones, and kept ones whose
          image a later decision deleted, and any with an image found under
          another name) or that are worth keeping (linked ones); not those
          of pixel-identical pairs or with an image found nowhere, and a file
          whose content is kept already (in the run or the --rescued
          store) is a hard link to that copy
--rescued recycle_rescue.py's store: where to look for an image the
          Recycle Bin no longer has

An image is found by its logged size and modification time, at its own path,
at the other image's path (a rename moves one onto the other), or in the
Recycle Bin of its drive under either path; reads only, one file at a time.
Scores come from core_search.py on WORK_DIR\\pairs, one search per setting
(a batch of pairs at a time for the settings with no candidate filter), the
aspect ratio filter off and sizes 1 to 99999 px as in the user's settings; a value is missing where
the setting doesn't pair the two (filtered out, or over the search's
threshold). Prints one line per pair: the decision, the
logged difference, each setting's value, and a * where the setting at its
default threshold disagrees with the decision (pairs a variant the user
kept, or misses a copy the user deleted); ? where an image is missing.
"""
import argparse
import csv
import datetime
import hashlib
import os
import re
import shutil
import struct
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import decisions_check as dc  # noqa: E402

# name, core_search arguments, the default threshold to judge by
SETTINGS = [
    ("ssim-32", ["--algorithm", "1", "--size", "32", "--threshold", "50"], 1.0),
    ("ssim-128", ["--algorithm", "1", "--size", "128", "--threshold", "50"], 1.0),
    ("mean-square", ["--algorithm", "0", "--size", "128", "--threshold", "15"], 5.0),
    ("local-colour", ["--algorithm", "3", "--size", "128", "--threshold", "50"], 4.0),
    ("butteraugli-768", ["--algorithm", "4", "--size", "128", "--threshold", "50", "--butteraugli-size", "768"], 12.0),
    ("aligned-768", ["--algorithm", "5", "--size", "128", "--threshold", "50", "--butteraugli-size", "768"], 12.0),
]
# Without a candidate filter a search at these thresholds pairs most of what it
# compares, and the core stops at resultCountMax results with the rest of the
# pairs unscored. A pair's value doesn't depend on the images around it, so
# these go a batch of pair folders at a time, too few to reach it. The
# Butteraugli searches stay whole: few results, and the aligned search's
# candidates depend on the collection, as in a real search.
WHOLE = ("butteraugli-768", "aligned-768")
BATCH = 100
LINE = re.compile(r"^([0-9.]+)  shows \S+  (.+?) \| (.+?)(?:  transform \d+)?$")


def recycle_bin(drive, cache={}):
    """{original path (lower case): [(size, $R path)]} for a drive's Recycle
    Bin, read from its $I files (format 2: version, size, deletion time,
    path length, UTF-16 path)."""
    if drive in cache:
        return cache[drive]
    found = {}
    root = os.path.join(drive + "\\", "$Recycle.Bin")
    try:
        folders = [os.path.join(root, d) for d in os.listdir(root)]
    except OSError:
        folders = []
    for folder in folders:
        try:
            names = os.listdir(folder)
        except OSError:
            continue
        for name in names:
            if not name.startswith("$I"):
                continue
            try:
                with open(os.path.join(folder, name), "rb") as f:
                    head = f.read(28)
                    version, size, _, length = struct.unpack("<qqqi", head)
                    if version != 2:
                        continue
                    path = f.read(length * 2).decode("utf-16-le").rstrip("\0")
            except (OSError, struct.error, UnicodeDecodeError):
                continue
            found.setdefault(path.lower(), []).append((size, os.path.join(folder, "$R" + name[2:])))
    cache[drive] = found
    return found


def logged_mtime(info):
    t = info.get("modified")
    return datetime.datetime.fromisoformat(t[:26].rstrip("Z")).replace(tzinfo=datetime.timezone.utc).timestamp() if t else None


def renames(events):
    """{old path: new path} from the log's renames of one image (RenameFirst,
    RenameSecond; the new path is the action's detail)."""
    moved = {}
    for e in events:
        if e["event"] == "action" and e.get("action") in ("RenameFirst", "RenameSecond") and e.get("detail"):
            for p in e.get("pairs", []):
                side = p["first"] if e["action"] == "RenameFirst" else p.get("second")
                if side:
                    moved[side["path"]] = e["detail"]
    return moved


def locate(info, other_path, moved, rescued=None, rescued_index=None):
    """The file now holding this image's content, and where it was found:
    its own path or where a rename took it; the other image's path (a
    replace moves one onto the other); the name the other image gave it in
    either folder (rename or move like the other); the Recycle Bin, by
    path or, as AntiDupl may recycle a file under a temporary name, by size
    and date alone; or recycle_rescue.py's store `rescued` (its index read
    once by the caller), once the bin no longer has it."""
    size, mtime = info["size"], logged_mtime(info)

    def same(path):
        try:
            st = os.stat(path)
        except OSError:
            return False
        return st.st_size == size and (mtime is None or abs(st.st_mtime - mtime) < 2)

    def final(path):
        seen = set()
        while path in moved and path not in seen:
            seen.add(path)
            path = moved[path]
        return path

    own = final(info["path"])
    candidates = [(own, "archive" if own == info["path"] else "archive, renamed")]
    if other_path:
        ext = os.path.splitext(info["path"])[1]
        stem = os.path.splitext(os.path.basename(other_path))[0]
        candidates += [(other_path, "archive, replaced the other"),
                       (final(other_path), "archive, replaced the other"),
                       (os.path.join(os.path.dirname(info["path"]), stem + ext), "archive, renamed like the other"),
                       (os.path.join(os.path.dirname(other_path), stem + ext), "archive, moved like the other")]
    for path, where in candidates:
        if same(path):
            return path, where
    drives = {p[:2].upper() for p in (info["path"], other_path) if p and len(p) > 1 and p[1] == ":"}
    for drive in sorted(drives):
        index = recycle_bin(drive)
        for path in (info["path"], other_path):
            for bin_size, r in index.get((path or "").lower(), []):
                if bin_size == size and same(r):
                    return r, "recycle bin"
        for entries in index.values():
            for bin_size, r in entries:
                if bin_size == size and same(r):
                    return r, "recycle bin, other name"
    if rescued:
        import recycle_rescue  # imports this module: not at the top
        copy = recycle_rescue.stored(rescued, info, rescued_index)
        if copy and os.path.exists(copy):
            return copy, "rescued"
    return None, "missing"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("log")
    ap.add_argument("work")
    ap.add_argument("--dll", required=True)
    ap.add_argument("--since")
    ap.add_argument("--keep")
    ap.add_argument("--rescued")
    a = ap.parse_args()

    events = dc.read_log(a.log)
    first_seen = {}
    for e in events:
        for p in dc.event_pairs(e):
            if "second" in p:
                first_seen.setdefault(dc.key(p), e["time"])
    pairs, decided = dc.replay(events)
    moved = renames(events)
    rescued_index = None
    if a.rescued:
        import recycle_rescue
        rescued_index = recycle_rescue.read_index(a.rescued)
    keys = sorted((k for k in decided if k in first_seen and pairs[k].get("second")), key=lambda k: first_seen[k])
    if a.since:
        keys = [k for k in keys if first_seen[k][:10] >= a.since]

    pair_dir = os.path.join(a.work, "pairs")
    os.makedirs(pair_dir, exist_ok=True)
    rows = []
    for n, k in enumerate(keys, 1):
        p = pairs[k]
        row = {"n": n, "decision": decided[k], "logged": p["difference"], "first": p["first"]["path"],
               "second": p["second"]["path"]}
        for side, info, other in (("a", p["first"], p["second"]["path"]), ("b", p["second"], p["first"]["path"])):
            src, where = locate(info, other, moved, a.rescued, rescued_index)
            row["from_" + side] = where
            if src:
                ext = os.path.splitext(info["path"])[1]
                dst = os.path.join(pair_dir, str(n), f"{n}{side}{ext}")
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                if not os.path.exists(dst):
                    shutil.copy2(src, dst)
        rows.append(row)
    with open(os.path.join(a.work, "pairs.tsv"), "w", encoding="utf-8", newline="\n") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]), delimiter="\t")
        w.writeheader()
        w.writerows(rows)

    scores = {r["n"]: {} for r in rows}
    folders = [os.path.join(pair_dir, d) for d in sorted(os.listdir(pair_dir))]
    for name, args, _ in SETTINGS:
        batches = [[pair_dir]] if name in WHOLE else [folders[i:i + BATCH] for i in range(0, len(folders), BATCH)]
        for batch in batches:
            out = subprocess.run([sys.executable, os.path.join(HERE, "core_search.py"), a.dll,
                                  os.path.join(a.work, "user-" + name), *batch, "--any-ratio",
                                  # the user's size limits: the core's default
                                  # maximum, 8196 px, leaves their tall
                                  # pictures unscored, which reads as a miss
                                  "--min-size", "1", "--max-size", "99999"] + args,
                                 capture_output=True, text=True, encoding="ascii", errors="replace").stdout
            for line in out.splitlines():
                m = LINE.match(line)
                if not m:
                    continue
                na, nb = (os.path.splitext(x)[0] for x in (m.group(2), m.group(3)))
                if na[:-1] == nb[:-1] and na[:-1].isdigit() and {na[-1], nb[-1]} == {"a", "b"}:
                    n = int(na[:-1])
                    scores[n][name] = min(scores[n].get(name, float("inf")), float(m.group(1)))

    with open(os.path.join(a.work, "scores.tsv"), "w", encoding="utf-8", newline="\n") as f:
        f.write("n\tdecision\tlogged\t" + "\t".join(s[0] for s in SETTINGS) + "\n")
        for r in rows:
            f.write(f"{r['n']}\t{r['decision']}\t{r['logged']}\t" +
                    "\t".join(str(scores[r["n"]].get(s[0], "")) for s in SETTINGS) + "\n")

    report = []

    def say(line=""):
        print(line)
        report.append(line)

    say(f"{'n':>3} {'decision':8} {'logged':>8} " + " ".join(f"{s[0]:>15}" for s in SETTINGS) + "  files")
    for r in rows:
        cells = []
        complete = "missing" not in (r["from_a"], r["from_b"])
        for name, _, threshold in SETTINGS:
            v = scores[r["n"]].get(name)
            paired = v is not None and v <= threshold
            wrong = (r["decision"] == "deleted" and not paired) or (r["decision"] == "mistake" and paired)
            mark = ("*" if wrong else " ") if complete else "?"
            cells.append(f"{'-' if v is None else f'{v:.3f}':>14}{mark}")
        files = "" if r["from_a"] == r["from_b"] == "archive" else f"{r['from_a']} / {r['from_b']}"
        say(f"{r['n']:>3} {r['decision']:8} {r['logged']:8.4f} " + " ".join(cells) + f"  {files}")

    say()
    say("At each setting's default threshold, over the pairs with both images:")
    whole = [r for r in rows if "missing" not in (r["from_a"], r["from_b"])]
    for name, _, threshold in SETTINGS:
        def paired(decision):
            sel = [r for r in whole if r["decision"] == decision]
            hit = sum(1 for r in sel if scores[r["n"]].get(name, float("inf")) <= threshold)
            return f"{hit} of {len(sel)}"
        say(f"  {name:16} (<= {threshold:g}): copies you deleted found {paired('deleted')}, "
            f"variants you kept paired {paired('mistake')}, linked pairs paired {paired('linked')}, "
            f"undecided pairs paired {paired('left')}")
    with open(os.path.join(a.work, "report.txt"), "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(report) + "\n")

    if a.keep:
        os.makedirs(os.path.join(a.keep, "pairs"), exist_ok=True)
        for name in ("pairs.tsv", "scores.tsv", "report.txt"):
            shutil.copy2(os.path.join(a.work, name), os.path.join(a.keep, name))
        known = {}
        if a.rescued:
            for f in (os.path.join(dp_, n) for dp_, _, names in os.walk(a.rescued) for n in names):
                if not f.endswith("index.tsv"):
                    known.setdefault(content_key(f), f)
        for d in (os.path.join(a.keep, "pairs", n) for n in os.listdir(os.path.join(a.keep, "pairs"))):
            for f in (os.path.join(d, n) for n in os.listdir(d)):
                known.setdefault(content_key(f), f)
        for r in rows:
            src = os.path.join(pair_dir, str(r["n"]))
            from_bin = "recycle bin" in r["from_a"] or "recycle bin" in r["from_b"]
            # Found under another name (the user renames kept versions): a
            # later run looks for the logged name and finds nothing.
            renamed = any(word in r[k] for word in ("renamed", "replaced") for k in ("from_a", "from_b"))
            # A pixel-identical pair (the GUI's 0.00) teaches nothing, and
            # nor does one whose other image was found nowhere.
            identical = r["logged"] is not None and float(r["logged"]) < IDENTICAL_MAX
            complete = os.path.isdir(src) and len(os.listdir(src)) == 2
            if (from_bin or renamed or r["decision"] in ("deleted", "linked")) and not identical and complete:
                dst = os.path.join(a.keep, "pairs", str(r["n"]))
                os.makedirs(dst, exist_ok=True)
                for name in os.listdir(src):
                    keep_file(os.path.join(src, name), os.path.join(dst, name), known)
    return 0


IDENTICAL_MAX = 0.00001


def content_key(path):
    h = hashlib.sha1()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return os.path.getsize(path), h.hexdigest()


def keep_file(src, dst, known):
    """Copies src to dst, or hard-links dst to a kept file of the same
    content (the same image in several pairs, both images of a byte-
    identical pair, a picture recycle_rescue.py stored): one copy on
    disk, which file comparers skip as a hard link. `known` maps
    content_key to a kept path and learns dst."""
    if os.path.exists(dst):
        return
    key = content_key(src)
    if key in known:
        try:
            os.link(known[key], dst)
            return
        except OSError:  # another volume, or the link limit
            pass
    shutil.copy2(src, dst)
    known.setdefault(key, dst)


if __name__ == "__main__":
    sys.exit(main())
