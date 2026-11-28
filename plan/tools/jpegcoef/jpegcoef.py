"""Reads and writes jpegcoef's .jcf files (the layout is in jpegcoef.c),
and runs the program on JPEG files.

    from jpegcoef import read_jpeg, write_jpeg
    j = read_jpeg("a.jpg", exe)   # dict: width, height, components
    write_jpeg(j, "b.jpg", exe)

Each component is a dict: h, v (sampling factors), table (index into
j["tables"]), coefs (int16 array [rows, columns, 8, 8], natural order).
j["tables"] is a list of four uint16 [8, 8] arrays or None.
"""
import os
import struct
import subprocess
import tempfile

import numpy as np


def read_jcf(path):
    with open(path, "rb") as f:
        data = f.read()
    if data[:4] != b"JCF1":
        raise ValueError("not a .jcf file")
    width, height, n = struct.unpack_from("<3i", data, 4)
    pos = 16
    comps = []
    for _ in range(n):
        h, v, table, wb, hb = struct.unpack_from("<5i", data, pos)
        pos += 20
        comps.append({"h": h, "v": v, "table": table, "wb": wb, "hb": hb})
    tables = []
    for _ in range(4):
        (present,) = struct.unpack_from("<i", data, pos)
        steps = np.frombuffer(data, "<u2", 64, pos + 4).reshape(8, 8).copy()
        pos += 4 + 128
        tables.append(steps if present else None)
    for c in comps:
        count = c["wb"] * c["hb"] * 64
        c["coefs"] = np.frombuffer(data, "<i2", count, pos).reshape(c["hb"], c["wb"], 8, 8).copy()
        pos += count * 2
    return {"width": width, "height": height, "components": comps, "tables": tables}


def write_jcf(j, path):
    out = [b"JCF1", struct.pack("<3i", j["width"], j["height"], len(j["components"]))]
    for c in j["components"]:
        hb, wb = c["coefs"].shape[:2]
        out.append(struct.pack("<5i", c["h"], c["v"], c["table"], wb, hb))
    for t in j["tables"]:
        out.append(struct.pack("<i", t is not None))
        out.append((np.zeros((8, 8)) if t is None else t).astype("<u2").tobytes())
    for c in j["components"]:
        out.append(np.ascontiguousarray(c["coefs"], dtype="<i2").tobytes())
    with open(path, "wb") as f:
        f.write(b"".join(out))


def read_jpeg(path, exe):
    with tempfile.TemporaryDirectory() as tmp:
        jcf = os.path.join(tmp, "a.jcf")
        subprocess.run([exe, "dump", path, jcf], check=True, capture_output=True)
        return read_jcf(jcf)


def write_jpeg(j, path, exe):
    with tempfile.TemporaryDirectory() as tmp:
        jcf = os.path.join(tmp, "a.jcf")
        write_jcf(j, jcf)
        subprocess.run([exe, "write", jcf, path], check=True, capture_output=True)
