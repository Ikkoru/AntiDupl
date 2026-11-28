"""Rebuilds a JPEG from a lossless file that was decoded from it (T40b):
the block grid, the chroma layout and the tables read from the pixels,
then each block's coefficients, so that jpegQS can work on a JPEG saved
as PNG as it would on the JPEG itself.

A JPEG stores each 8 x 8 block's DCT coefficients as multiples of its
table's steps, and decoding only rounds the result to 8 bits; the
transform keeps the rounding's size, so the decoded pixels transformed
again on the right grid land each coefficient within a fraction of its
step, and rounding gives it back. How it is read:

* The decoder's own 8-bit Y, Cb and Cr planes, per pixel the integers that
  libjpeg's conversion turns into exactly that RGB (decoder_planes), which
  recomputing them in floating point misses by up to a level in colour.
* The block grid where the luma's jumps between neighbours peak every
  8 pixels; for half-resolution chroma also its 16 px phase.
* Each chroma layout (full resolution; half, blown up by libjpeg's
  "fancy" filter or by repeating samples) and IJG quality is tried by
  rebuilding a central window, decoding it again as libjpeg does (its
  IDCT's rounding, its upsampling's integer arithmetic, its colour
  tables) and counting the pixels it misses. Any finer table fits too,
  so the file's own shows as a sharp drop in misses at the coarsest
  quality that fits (luma_quality); one quality for both tables is tried
  first, as encoders nearly always use one.
* Only libjpeg's scaled standard tables are tried, which most real JPEGs
  use (plan 08); a file with other tables gets none read.

The finer steps of high qualities drown in the rounding (plan 08 says from
where). Blocks the decoder clipped at 0 or 255 come back with errors. A decoder with another IDCT (libjpeg's fast one) is not
read reliably.

    py -3 jpeg_from_pixels.py <in.png> <out.jpg> --exe <jpegcoef.exe>
        [--sampling auto|444|fancy|nearest] [--tables <reference.jpg>] [--report]

--tables takes the tables from a JPEG instead of reading them (to measure
the coefficients alone). --report prints what was found. The output
covers the input from the grid's first whole block: a file cropped off
the grid loses its first, partial rows and columns of blocks.
"""
import argparse
import os
import sys

import numpy as np
from PIL import Image
from scipy import fft

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "jpegcoef"))
import jpegcoef  # noqa: E402

Image.MAX_IMAGE_PIXELS = None

# The standard tables (ITU T.81 Annex K), natural order, which libjpeg
# scales by quality (ijg_table).
STD_LUMA = np.array([
    16, 11, 10, 16, 24, 40, 51, 61, 12, 12, 14, 19, 26, 58, 60, 55,
    14, 13, 16, 24, 40, 57, 69, 56, 14, 17, 22, 29, 51, 87, 80, 62,
    18, 22, 37, 56, 68, 109, 103, 77, 24, 35, 55, 64, 81, 104, 113, 92,
    49, 64, 78, 87, 103, 121, 120, 101, 72, 92, 95, 98, 112, 100, 103, 99], float).reshape(8, 8)
STD_CHROMA = np.array([
    17, 18, 24, 47, 99, 99, 99, 99, 18, 21, 26, 66, 99, 99, 99, 99,
    24, 26, 56, 99, 99, 99, 99, 99, 47, 66, 99, 99, 99, 99, 99, 99] + [99] * 32, float).reshape(8, 8)


def to_ycc(rgb):
    """libjpeg's RGB to YCbCr, unrounded."""
    r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    y = 0.299 * r + 0.587 * g + 0.114 * b
    cb = -0.168735892 * r - 0.331264108 * g + 0.5 * b + 128
    cr = 0.5 * r - 0.418687589 * g - 0.081312411 * b + 128
    return y, cb, cr


def blocks_dct(plane):
    """Orthonormal 8 x 8 DCTs of a plane whose sides are multiples of 8,
    the pixels shifted by -128: JPEG's own coefficients before rounding."""
    h, w = plane.shape
    b = plane.reshape(h // 8, 8, w // 8, 8).transpose(0, 2, 1, 3)
    return fft.dctn(b - 128.0, axes=(2, 3), norm="ortho")


def fancy_up_1d(n_in, n_out):
    """The matrix of libjpeg's fancy upsampling by 2 along one axis: the
    nearer input sample 3/4, the next 1/4, the edge samples repeated."""
    from scipy import sparse
    i = np.arange(n_out)
    k = np.minimum(i // 2, n_in - 1)
    other = np.clip(np.where(i % 2 == 0, k - 1, k + 1), 0, n_in - 1)
    return sparse.coo_matrix((np.r_[np.full(n_out, 0.75), np.full(n_out, 0.25)], (np.r_[i, i], np.r_[k, other])),
                             shape=(n_out, n_in)).tocsr()


def nearest_up_1d(n_in, n_out):
    from scipy import sparse
    i = np.arange(n_out)
    return sparse.coo_matrix((np.ones(n_out), (i, np.minimum(i // 2, n_in - 1))), shape=(n_out, n_in)).tocsr()


def downsampled(plane, how):
    """The half-resolution plane the decoder blew up into `plane`, by
    least squares along each axis (the filters are separable)."""
    from scipy.linalg import solveh_banded
    up = fancy_up_1d if how == "fancy" else nearest_up_1d

    def solve_axis(p):
        # Normal equations A^T A x = A^T p; A^T A is tridiagonal, as each
        # output sample mixes two neighbouring inputs.
        n_out = p.shape[0]
        a = up((n_out + 1) // 2, n_out)
        ata = (a.T @ a).tocsr()
        n = ata.shape[0]
        ab = np.zeros((2, n))
        ab[1] = ata.diagonal(0)
        ab[0, 1:] = ata.diagonal(1)
        return solveh_banded(ab, a.T @ p)

    return solve_axis(solve_axis(plane).T).T


def grid_offset(y):
    """The block grid's offset: where the luma's jumps between neighbours
    peak every 8 pixels."""
    jx = np.abs(np.diff(y, axis=1)).mean(axis=0)
    jy = np.abs(np.diff(y, axis=0)).mean(axis=1)
    ox = int(np.argmax([jx[(np.arange(len(jx)) + 1) % 8 == c].mean() for c in range(8)]))
    oy = int(np.argmax([jy[(np.arange(len(jy)) + 1) % 8 == c].mean() for c in range(8)]))
    return ox, oy


def clean_blocks(planes_rgb_blocks):
    """Blocks with no clipped pixel: clipping breaks the relation to the
    steps there."""
    return (planes_rgb_blocks.min(axis=(2, 3, 4)) > 0) & (planes_rgb_blocks.max(axis=(2, 3, 4)) < 255)


def ijg_table(std, quality):
    """libjpeg's table for a quality (jpeg_quality_scaling, then
    jpeg_add_quant_table with force_baseline)."""
    scale = 5000 // quality if quality < 50 else 200 - 2 * quality
    return np.clip((std * scale + 50) // 100, 1, 255)


def decoded_plane(coefs, table):
    """A plane decoded from quantised blocks: dequantised, inverse DCT,
    shifted back, rounded and clipped to 8 bits, as a decoder outputs it
    before any upsampling."""
    b = fft.idctn(coefs * table, axes=(2, 3), norm="ortho") + 128.0
    hb, wb = b.shape[:2]
    # Half up, as libjpeg's descaling does: flat chroma often lands on
    # exactly .5, where numpy's round-half-to-even would differ.
    return np.clip(np.floor(b.transpose(0, 2, 1, 3).reshape(hb * 8, wb * 8) + 0.5), 0, 255)


def upsampled(half, how, shape):
    """A decoded half-resolution plane blown up to `shape` as libjpeg
    does it: "nearest" repeats each sample; "fancy" is h2v2_fancy_upsample's
    integer arithmetic (3/4 and 1/4 vertically, then horizontally, the
    edges repeated, rounded with alternating biases 8 and 7)."""
    h = half.astype(np.int64)
    if how == "nearest":
        return np.repeat(np.repeat(h, 2, axis=0), 2, axis=1)[:shape[0], :shape[1]].astype(np.float64)
    above = np.vstack([h[:1], h[:-1]])
    below = np.vstack([h[1:], h[-1:]])
    cols = np.empty((2 * h.shape[0], h.shape[1]), np.int64)
    cols[0::2] = 3 * h + above
    cols[1::2] = 3 * h + below
    left = np.hstack([cols[:, :1], cols[:, :-1]])
    right = np.hstack([cols[:, 1:], cols[:, -1:]])
    out = np.empty((cols.shape[0], 2 * cols.shape[1]), np.int64)
    out[:, 0::2] = (3 * cols + left + 8) >> 4
    out[:, 1::2] = (3 * cols + right + 7) >> 4
    return out[:shape[0], :shape[1]].astype(np.float64)


def ycc_to_rgb(y, cb, cr):
    """libjpeg's YCbCr to RGB (jdcolor.c's fixed-point tables, 16 bits),
    on integer planes, clipped to 8 bits."""
    one_half, fix = 1 << 15, lambda v: int(v * 65536 + 0.5)
    x, z = cb.astype(np.int64) - 128, cr.astype(np.int64) - 128
    yi = y.astype(np.int64)
    r = yi + ((fix(1.40200) * z + one_half) >> 16)
    g = yi + ((-fix(0.34414) * x - fix(0.71414) * z + one_half) >> 16)
    b = yi + ((fix(1.77200) * x + one_half) >> 16)
    return np.clip(np.stack([r, g, b], axis=-1), 0, 255).astype(np.float64)


# How far a rebuilt chroma plane may miss a pixel and still count as
# matching it, when the chroma layout is chosen: where decoder_planes
# found no unique triplet, the chroma is the floating-point estimate,
# up to a level off, and blowing it up again by the filter adds to that.
# Luma is judged in RGB instead (Window.luma_misfit), a level apart.
CHROMA_TOL = 1.5


class Window:
    """A part of the picture on one candidate grid: its planes, the
    unclipped pixels, and the coefficients for a chroma layout."""

    def __init__(self, rgb, ycc, x0, y0, h, w, how):
        self.how = how
        sub = rgb[y0:y0 + h, x0:x0 + w]
        self.rgb = sub
        self.y, self.cb, self.cr = (p[y0:y0 + h, x0:x0 + w] for p in ycc)
        blocks = clean_blocks(sub.reshape(h // 8, 8, w // 8, 8, 3).transpose(0, 2, 1, 3, 4))
        self.clean_px = np.repeat(np.repeat(blocks, 8, axis=0), 8, axis=1)
        self.ycoef = blocks_dct(self.y)
        if how == "444":
            self.cbcoef, self.crcoef = blocks_dct(self.cb), blocks_dct(self.cr)
        else:
            self.cbcoef = blocks_dct(downsampled(self.cb, how))
            self.crcoef = blocks_dct(downsampled(self.cr, how))

    def chroma_misfit(self, t):
        bad = 0.0
        for coefs, obs in ((self.cbcoef, self.cb), (self.crcoef, self.cr)):
            plane = decoded_plane(np.round(coefs / t), t)
            if self.how != "444":
                plane = upsampled(plane, self.how, obs.shape)
            bad += np.mean(np.abs(plane - obs)[self.clean_px] > CHROMA_TOL) / 2
        return float(bad)

    def decoded_chroma(self, t):
        """The chroma planes a decoder would give for table t, at full
        size: decoded, then blown up by the layout's filter."""
        out = []
        for coefs, obs in ((self.cbcoef, self.cb), (self.crcoef, self.cr)):
            plane = decoded_plane(np.round(coefs / t), t)
            out.append(plane if self.how == "444" else upsampled(plane, self.how, obs.shape))
        return out

    def luma_misfit(self, t, chroma):
        """The share of unclipped pixels whose RGB, decoded with luma table
        t and the given chroma planes and converted as libjpeg does, misses
        the picture's by more than a level in any channel. Judged in RGB
        because luma recomputed from 8-bit RGB is up to a level off in
        colourful areas, which hides a coarser table's misses."""
        y = decoded_plane(np.round(self.ycoef / t), t)
        rgb = ycc_to_rgb(y, chroma[0], chroma[1])
        return float(np.mean((np.abs(rgb - self.rgb).max(axis=-1) > 1)[self.clean_px]))


def luma_quality(curve):
    """The IJG quality of the luma table from the misfit of every quality
    (curve[q - 1]). Coarser tables than the file's miss many pixels, and
    any finer one fits, so the file's own shows as a sharp drop, the first
    quality that misfits several times less than the coarser ones before it
    (the worst of the three: a neighbour sharing most of the file's table
    can take part of the drop). Neighbouring qualities can share most of a
    table: the lowest misfit of that run. None without a drop: not a
    decoded JPEG, or a table not of IJG's kind."""
    for q in range(2, 101):
        m = curve[q - 1]
        prev = max(curve[max(0, q - 4):q - 1])
        if m < DROP_FLOOR and m * DROP_RATIO < prev:
            run = [q]
            while run[-1] < 100 and curve[run[-1]] < max(2 * m, m + 0.0005):
                run.append(run[-1] + 1)
            best = min(curve[k - 1] for k in run)
            ties = [k for k in run if curve[k - 1] == best]
            return ties[len(ties) // 2]
    return None


# A drop to under this misfit, by this factor, marks the file's quality.
DROP_FLOOR = 0.03
DROP_RATIO = 8
# A chroma table within this misfit of the best one fits as well.
CHROMA_SLACK = 0.0002


def decoder_planes(rgb):
    """The 8-bit Y, Cb and Cr planes a libjpeg decoder converted into
    these RGB pixels: per pixel, the integers within one of the unrounded
    estimate that its conversion maps to exactly this RGB. Far less noisy
    than the estimate itself, whose chroma is up to a level off. Where no
    triplet or several do (another decoder's conversion, clipped colours),
    the estimate stays."""
    est = [np.round(p) for p in to_ycc(rgb)]
    found = [p.copy() for p in est]
    count = np.zeros(rgb.shape[:2], np.int8)
    for dy in (0, -1, 1):
        for db in (0, -1, 1):
            for dr in (0, -1, 1):
                y, cb, cr = (np.clip(p + d, 0, 255) for p, d in zip(est, (dy, db, dr)))
                hit = (ycc_to_rgb(y, cb, cr) == rgb).all(axis=-1)
                first = hit & (count == 0)
                for f, v in zip(found, (y, cb, cr)):
                    f[first] = v[first]
                count += hit
    exact = count == 1
    raw = to_ycc(rgb)
    return tuple(np.where(exact, f, r) for f, r in zip(found, raw)), exact


def rebuild(rgb, sampling="auto", tables=None, report=False, window=384):
    """The JPEG (a jpegcoef dict) the pixels were most likely decoded
    from, the grid offset and chroma layout used, and the IJG qualities
    read (None for one that didn't fit). The layout and tables are chosen
    on a central window; the coefficients then cover the whole picture
    from the grid's first whole block."""
    rgb = rgb.astype(np.float64)
    ycc, _ = decoder_planes(rgb)
    ox, oy = grid_offset(ycc[0])
    H, W = ycc[0].shape
    side = min(window, (H - 32) // 16 * 16, (W - 32) // 16 * 16)
    if side < 32:
        raise ValueError("too small")
    cy, cx = (H - side) // 2 // 16 * 16, (W - side) // 2 // 16 * 16
    layouts = [("444", 0, 0)] + [(how, px, py) for how in ("fancy", "nearest") for py in (0, 8) for px in (0, 8)]
    if sampling != "auto":
        layouts = [l for l in layouts if l[0] == sampling]
    cands = []
    for how, px, py in layouts:
        gx, gy = (ox + px) % 16, (oy + py) % 16
        win = Window(rgb, ycc, cx + gx, cy + gy, side, side, how)
        if tables is not None:
            cands.append(((win.chroma_misfit(tables[1]), 0), how, gx, gy, win, None))
            continue
        ccurve = [win.chroma_misfit(ijg_table(STD_CHROMA, q)) for q in range(1, 101)]
        floor = min(ccurve)
        qc = next(q for q in range(1, 101) if ccurve[q - 1] <= floor + CHROMA_SLACK)
        # The right layout reaches the floor, near nothing, with the
        # coarsest table; a wrong one only with a finer table, or never.
        cands.append(((floor > 0.002, qc, how != "444", how != "fancy"), how, gx, gy, win, ccurve))
    cands.sort(key=lambda c: c[0])
    _, how, gx, gy, win, ccurve = cands[0]
    if tables is None:
        # Encoders nearly always set one quality for both tables: judged
        # together in RGB, the file's own layout and quality show a sharp
        # drop to near no misfit. Every layout whose chroma comes close
        # enough is tried: off the grid, the chroma curve alone can rank
        # the file's own 16 px phase below others.
        joint_best = None
        for c in [c for c in cands if not c[0][0]] or cands[:1]:
            w_ = c[4]
            joint = [w_.luma_misfit(ijg_table(STD_LUMA, q), w_.decoded_chroma(ijg_table(STD_CHROMA, q)))
                     for q in range(1, 101)]
            q_ = luma_quality(joint)
            # Any layout fits with a fine enough table: the file's own is the
            # one that fits with the coarsest.
            if q_ is not None and (joint_best is None or (q_, joint[q_ - 1]) < joint_best[:2]):
                joint_best = (q_, joint[q_ - 1], c)
        if joint_best is not None:
            qy, _, c = joint_best
            _, how, gx, gy, win, ccurve = c
            qc = qy
        else:
            qy = None
            qc = cands[0][0][1]
            chroma = win.decoded_chroma(ijg_table(STD_CHROMA, qc))
            qy = luma_quality([win.luma_misfit(ijg_table(STD_LUMA, q), chroma) for q in range(1, 101)])
        ty = ijg_table(STD_LUMA, qy) if qy else np.ones((8, 8))
        tcb = ijg_table(STD_CHROMA, qc)
    else:
        qy = qc = None
        ty, tcb = tables
    h16, w16 = (H - gy) // 16 * 16, (W - gx) // 16 * 16
    full = Window(rgb, ycc, gx, gy, h16, w16, how)
    q = lambda c, t: np.clip(np.round(c / t), -32767, 32767).astype(np.int16)
    sub = 1 if how == "444" else 2
    ty, tcb = np.asarray(ty).astype(np.uint16), np.asarray(tcb).astype(np.uint16)
    j = {"width": w16, "height": h16,
         "components": [{"h": sub, "v": sub, "table": 0, "coefs": q(full.ycoef, ty)},
                        {"h": 1, "v": 1, "table": 1, "coefs": q(full.cbcoef, tcb)},
                        {"h": 1, "v": 1, "table": 1, "coefs": q(full.crcoef, tcb)}],
         "tables": [ty, tcb, None, None]}
    if report:
        print(f"grid offset {gx},{gy}; chroma {how}; luma quality {qy}, chroma quality {qc}")
    return j, (gx, gy), how, (qy, qc)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("src")
    ap.add_argument("dst")
    ap.add_argument("--exe", required=True)
    ap.add_argument("--sampling", default="auto")
    ap.add_argument("--tables")
    ap.add_argument("--report", action="store_true")
    a = ap.parse_args()
    rgb = np.asarray(Image.open(a.src).convert("RGB"))
    tables = None
    if a.tables:
        ref = jpegcoef.read_jpeg(a.tables, a.exe)
        tables = (ref["tables"][ref["components"][0]["table"]], ref["tables"][ref["components"][1]["table"]])
    j, offset, how, qualities = rebuild(rgb, a.sampling, tables, a.report)
    jpegcoef.write_jpeg(j, a.dst, a.exe)


if __name__ == "__main__":
    main()
