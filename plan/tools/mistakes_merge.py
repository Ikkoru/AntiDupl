"""Adds one mistakes list (mistakes.adm) to another, leaving out the pairs
and single images the target already holds.

Reads both files with its own parser of the format (adMistakeStorage.cpp,
adFileStream.cpp), writes the entries the target lacks to a scratch file
in that format, then has the core load the target and that file and save
the union: the core's own reader checks every record (a path whose stored
hash doesn't match fails the load), and the result is sorted as the
program writes it. Writes --out, never the target; replacing the target,
after a backup, is the caller's step. Refuses while any AntiDupl runs: the
program writes its list when it closes, over the merge.

    py -3 mistakes_merge.py <target mistakes.adm> <source mistakes.adm> --dll <bin\\Release> --out <merged.adm>
"""
import argparse
import ctypes
import os
import struct
import subprocess
import sys
import tempfile

AD_FILE_MISTAKE_DATA_BASE = 2
MAGIC = b"adm"


def read_string(b, o):
    n = struct.unpack_from("<Q", b, o)[0]
    o += 8
    return b[o:o + 2 * n].decode("utf-16-le"), o + 2 * n


def read_info(b, o, version):
    """One TImageInfo as TInputFileStream::Load reads it: the key the core
    compares (path, size, time, hash), the record's bytes, the next offset."""
    start = o
    path, o = read_string(b, o)
    size, mtime, crc = struct.unpack_from("<QQI", b, o)
    o += 20 + 12               # type, width, height
    if version > 1:
        o += 8                 # blockiness
    if version > 2:
        o += 8                 # blurring
    if version > 3:
        o += 1                 # exif: isEmpty, then seven strings
        for _ in range(7):
            _, o = read_string(b, o)
    return (path.casefold(), size, mtime, crc), b[start:o], o


def read_list(path):
    b = open(path, "rb").read()
    if b[:3] != MAGIC:
        sys.exit(f"{path}: not a mistakes list")
    version = struct.unpack_from("<I", b, 3)[0]
    o = 7
    singles, pairs = {}, {}
    n = struct.unpack_from("<Q", b, o)[0]
    o += 8
    for _ in range(n):
        key, raw, o = read_info(b, o, version)
        singles[key] = raw
    n = struct.unpack_from("<Q", b, o)[0]
    o += 8
    for _ in range(n):
        k1, r1, o = read_info(b, o, version)
        k2, r2, o = read_info(b, o, version)
        # The core stores a pair in path order; the key ignores the order.
        pairs[tuple(sorted((k1, k2)))] = r1 + r2
    if o != len(b):
        sys.exit(f"{path}: {len(b) - o} bytes after the last record; format not understood")
    return version, singles, pairs


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("target")
    ap.add_argument("source")
    ap.add_argument("--dll", required=True, help="folder holding AntiDupl.dll (bin\\Release)")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()

    running = subprocess.run(["tasklist", "/fo", "csv", "/nh"], capture_output=True, text=True).stdout
    if "antidupl" in running.lower():
        sys.exit("an AntiDupl is running: close it first (it writes its mistakes list on close)")

    tv, tsingles, tpairs = read_list(a.target)
    sv, ssingles, spairs = read_list(a.source)
    if tv != sv:
        sys.exit(f"file versions differ (target {tv}, source {sv}); open the older one in the newer build first")
    add_singles = {k: r for k, r in ssingles.items() if k not in tsingles}
    add_pairs = {k: r for k, r in spairs.items() if k not in tpairs}
    print(f"target: {len(tsingles)} singles, {len(tpairs)} pairs; source: {len(ssingles)} singles, {len(spairs)} pairs")
    print(f"adding {len(add_singles)} singles, {len(add_pairs)} pairs (the rest the target holds)")

    with tempfile.TemporaryDirectory() as work:
        added = os.path.join(work, "added.adm")
        with open(added, "wb") as f:
            f.write(MAGIC + struct.pack("<I", sv))
            f.write(struct.pack("<Q", len(add_singles)) + b"".join(add_singles.values()))
            f.write(struct.pack("<Q", len(add_pairs)) + b"".join(add_pairs.values()))
        user = os.path.join(work, "user")
        os.mkdir(user)
        # In a child process: the core keeps the user folder's statistics
        # file open until its process ends, and the folder can't be removed
        # before that.
        if subprocess.call([sys.executable, os.path.abspath(__file__), "--core", os.path.abspath(a.dll), user,
                            os.path.abspath(a.target), added, os.path.abspath(a.out)]):
            sys.exit("the core step failed: target untouched")

    ov, osingles, opairs = read_list(a.out)
    want_singles, want_pairs = set(tsingles) | set(ssingles), set(tpairs) | set(spairs)
    if set(osingles) != want_singles or set(opairs) != want_pairs:
        sys.exit("the merged list is not the union of the two: left as it is for a look, target untouched")
    print(f"wrote {a.out}: {len(osingles)} singles, {len(opairs)} pairs, the union of both")


def core_merge(dll, user, target, added, out):
    core = ctypes.CDLL(os.path.join(dll, "AntiDupl.dll"))
    core.adCreateW.restype = ctypes.c_void_p
    core.adCreateW.argtypes = [ctypes.c_wchar_p]
    core.adRelease.argtypes = [ctypes.c_void_p]
    core.adLoadW.argtypes = [ctypes.c_void_p, ctypes.c_int32, ctypes.c_wchar_p, ctypes.c_int32]
    core.adSaveW.argtypes = [ctypes.c_void_p, ctypes.c_int32, ctypes.c_wchar_p]
    h = core.adCreateW(user)
    if not h:
        sys.exit("adCreateW failed")
    try:
        # Load adds to what the engine holds; check 0 keeps the entries of
        # files that no longer exist, as the target holds them.
        for path in (target, added):
            err = core.adLoadW(h, AD_FILE_MISTAKE_DATA_BASE, path, 0)
            if err:
                sys.exit(f"the core refused {path}: error {err}")
        err = core.adSaveW(h, AD_FILE_MISTAKE_DATA_BASE, out)
        if err:
            sys.exit(f"the core could not write {out}: error {err}")
    finally:
        core.adRelease(h)


if __name__ == "__main__":
    if sys.argv[1:2] == ["--core"]:
        core_merge(*sys.argv[2:7])
    else:
        main()
