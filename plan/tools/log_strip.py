"""Takes the `result` lines out of a decision log, for a log written before
schema 4: they were nearly all of its size, and nothing reads them. Every other
line keeps its bytes and its place, which the replay depends on.

Usage: py -3 log_strip.py <decisions.jsonl>

Close the program first. The original is kept beside the log as
<decisions.jsonl>.original.xz, and is checked by decompressing it before the log
is touched. Compressing takes several minutes. Refuses a log whose archive
already exists, and one that has no result lines; leaves the log as it was if
any check fails or the log changes meanwhile.

The archive stays until its owner drops it. To read it again:
    py -3 -c "import lzma,shutil,sys; shutil.copyfileobj(lzma.open(sys.argv[1]), open(sys.argv[2],'wb'))" <archive> <output>
"""
import hashlib
import lzma
import os
import subprocess
import sys

PROGRAM = "AntiDupl.NET.WinForms.exe"
RESULT = b'"event":"result"'
HEAD = 120  # the event name comes within this many bytes of a line's start


def program_running():
    out = subprocess.run(["tasklist", "/fi", f"imagename eq {PROGRAM}"], capture_output=True, text=True, errors="replace").stdout
    return PROGRAM.lower() in out.lower()


def compress(data):
    return lzma.compress(data, preset=9 | lzma.PRESET_EXTREME)


def stripped_lines(data):
    lines = data.splitlines(keepends=True)
    kept = [line for line in lines if RESULT not in line[:HEAD]]
    return lines, kept


def strip(path):
    archive = path + ".original.xz"
    if program_running():
        sys.exit(f"{PROGRAM} is running: close it first, or it may write to the log meanwhile")
    if os.path.exists(archive):
        sys.exit(f"there is already an archive: {archive}")
    before = os.stat(path)
    with open(path, "rb") as f:
        data = f.read()
    lines, kept = stripped_lines(data)
    if len(kept) == len(lines):
        sys.exit("no result lines in this log")
    digest = hashlib.sha256(data).hexdigest()
    print(f"{len(data) / 1e6:.1f} MB, {len(lines)} lines, {len(lines) - len(kept)} of them results; compressing the original, some minutes")

    temporary = archive + ".tmp"
    with open(temporary, "wb") as f:
        f.write(compress(data))
    try:
        with open(temporary, "rb") as f:
            archived = hashlib.sha256(lzma.decompress(f.read())).hexdigest()
    except lzma.LZMAError:
        archived = None
    if archived != digest:
        os.remove(temporary)
        sys.exit("the archive doesn't decompress to the log: nothing changed")

    stripped = path + ".stripped.tmp"
    with open(stripped, "wb") as f:
        f.writelines(kept)
    with open(stripped, "rb") as f:
        written = f.read().splitlines(keepends=True)
    if written != kept or any(RESULT in line[:HEAD] for line in written):
        os.remove(stripped)
        os.remove(temporary)
        sys.exit("the stripped log isn't the log without its result lines: nothing changed")

    after = os.stat(path)
    if (after.st_size, after.st_mtime_ns) != (before.st_size, before.st_mtime_ns):
        os.remove(stripped)
        os.remove(temporary)
        sys.exit("the log changed meanwhile: nothing changed")
    os.replace(temporary, archive)
    os.replace(stripped, path)
    print(f"log {sum(map(len, kept)) / 1e6:.1f} MB, {len(kept)} lines; original kept as {archive}, {os.path.getsize(archive) / 1e6:.1f} MB")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    strip(sys.argv[1])
