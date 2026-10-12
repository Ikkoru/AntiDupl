"""Builds and extends the sample set of the study (plan 07): one folder per
case. A generated case holds an artist's original, the artist's variants
and work-in-progress steps (copied out of the archive, read only), and
copies, crops, overlays, transforms and edits derived from the original.
Cases added by hand (pairs the user picked) sit beside them with a
manifest written by hand.

Usage: py -3 study_set.py <config .json> <set folder> [--rebuild]

The config names files in the user's archive, so it is kept outside this
repository (on the user's PC: the workspace's Research\\study_set.json):
    {"archive": "<folder>",
     "cases": [{"name": "<case>", "original": "<path>",
                "variants": ["<path>", ...], "steps": ["<path>", ...]}]}
Paths are relative to the archive; steps in drawing order.

Each case folder has manifest.tsv, one row per file:
    file, kind, detail, origin, scale, quality, generations, kept
kind: original, variant, step, copy, crop, overlay, gray, transform, edit.
The last four columns describe how a derived file was made from the
original, for the "which copy is worse" task: scale (1 = full size, the
detail kept even when resized back up), quality (JPEG/WebP/AVIF quality,
100 = lossless, or "jxl-d<distance>"), generations (times encoded), kept
(share of the original's area still in the picture). Existing
files are kept unless --rebuild; the manifest is rewritten each run.

The set is not disposable: the user's hand-added cases can't be rebuilt,
so it has no CACHEDIR.TAG.
"""
import argparse
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile

import numpy as np
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont

Image.MAX_IMAGE_PIXELS = None
CJXL = os.environ.get("CJXL", "cjxl")
FIELDS = ["file", "kind", "detail", "origin", "scale", "quality", "generations", "kept"]


def rgb(im):
    return im.convert("RGB")


def jpeg_bytes(im, quality, subsampling):
    buf = io.BytesIO()
    rgb(im).save(buf, "JPEG", quality=quality, subsampling=subsampling, optimize=True)
    return buf.getvalue()


def save_jpeg(im, path, quality, subsampling=2, generations=1):
    data = jpeg_bytes(im, quality, subsampling)
    for _ in range(generations - 1):
        data = jpeg_bytes(Image.open(io.BytesIO(data)), quality, subsampling)
    with open(path, "wb") as f:
        f.write(data)


def resized(im, factor, method=Image.LANCZOS):
    return im.resize((max(1, round(im.width * factor)), max(1, round(im.height * factor))), method)


def box(im, x0, y0, x1, y1):
    return (round(im.width * x0), round(im.height * y0), round(im.width * x1), round(im.height * y1))


def detailed_box(im, w, h, avoid=None):
    """The w x h (fractions of the image) region with the most detail (sum
    of gradient magnitudes on a 256 px copy), so an edit lands where it
    changes something; `avoid` (fractions) is a region not to overlap."""
    g = np.asarray(im.convert("L").resize((256, round(256 * im.height / im.width)), Image.BOX), dtype=np.float64)
    energy = np.abs(np.diff(g, axis=0))[:, :-1] + np.abs(np.diff(g, axis=1))[:-1, :]
    integral = np.pad(energy.cumsum(0).cumsum(1), ((1, 0), (1, 0)))
    bh, bw = max(1, round(h * energy.shape[0])), max(1, round(w * energy.shape[1]))
    sums = integral[bh:, bw:] - integral[:-bh, bw:] - integral[bh:, :-bw] + integral[:-bh, :-bw]
    if avoid:
        ys, xs = np.mgrid[0:sums.shape[0], 0:sums.shape[1]]
        ax0, ay0, ax1, ay1 = (avoid[0] * energy.shape[1], avoid[1] * energy.shape[0],
                              avoid[2] * energy.shape[1], avoid[3] * energy.shape[0])
        overlap = (xs < ax1) & (xs + bw > ax0) & (ys < ay1) & (ys + bh > ay0)
        sums = np.where(overlap, -1, sums)
    y, x = np.unravel_index(np.argmax(sums), sums.shape)
    fx, fy = x / energy.shape[1], y / energy.shape[0]
    return (fx, fy, fx + w, fy + h)


def frac_box(im, f):
    return box(im, *f)


def mosaic(im, region, cell):
    out = rgb(im)
    part = out.crop(region)
    small = part.resize((max(1, part.width // cell), max(1, part.height // cell)), Image.BOX)
    out.paste(small.resize(part.size, Image.NEAREST), region[:2])
    return out


def hue_shift(im, degrees, region=None):
    out = rgb(im)
    part = out.crop(region) if region else out
    h, s, v = part.convert("HSV").split()
    shift = round(degrees / 360 * 256)
    h = h.point(lambda x: (x + shift) % 256)
    shifted = Image.merge("HSV", (h, s, v)).convert("RGB")
    if region:
        out.paste(shifted, region[:2])
        return out
    return shifted


def text(im, words, size_frac, xy_frac, fill, opacity=255):
    out = rgb(im).convert("RGBA")
    layer = Image.new("RGBA", out.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    size = max(12, round(im.width * size_frac))
    font = ImageFont.load_default(size=size)
    w = draw.textlength(words, font=font)
    x = round(im.width * xy_frac[0] - (w / 2 if xy_frac[0] == 0.5 else 0))
    y = round(im.height * xy_frac[1]) - size // 2
    draw.text((x, y), words, fill=fill + (opacity,), font=font)
    return Image.alpha_composite(out, layer).convert("RGB")


def bar(im, region):
    out = rgb(im)
    ImageDraw.Draw(out).rectangle(region, fill=(0, 0, 0))
    return out


def clone_patch(im, src_frac, dst_frac):
    """A detailed region copied over another one: a local structural
    change of the kind an artist's variant makes."""
    out = rgb(im)
    patch = out.crop(frac_box(im, src_frac))
    out.paste(patch, frac_box(im, dst_frac)[:2])
    return out


def smudge(im, region, radius):
    out = rgb(im)
    part = out.crop(region).filter(ImageFilter.GaussianBlur(radius))
    out.paste(part, region[:2])
    return out


def cropped(im, left, top, right, bottom):
    return im.crop(box(im, left, top, 1 - right, 1 - bottom))


def padded(im, frac, colour):
    pad = round(max(im.width, im.height) * frac)
    out = Image.new("RGB", (im.width + 2 * pad, im.height + 2 * pad), colour)
    out.paste(rgb(im), (pad, pad))
    return out


def centre_square(im):
    side = min(im.width, im.height)
    left, top = (im.width - side) // 2, (im.height - side) // 2
    return im.crop((left, top, left + side, top + side))


def jxl(im, path, distance):
    with tempfile.TemporaryDirectory(dir=os.path.dirname(path)) as tmp:
        src = os.path.join(tmp, "in.png")
        rgb(im).save(src)
        subprocess.run([CJXL, "-d", str(distance), "--quiet", src, path], check=True)


def png(im, p):
    rgb(im).save(p + ".png")


# name, kind, detail, (scale, quality, generations, kept), maker(original, path without extension)
def derived(original):
    o = original
    edit_area = detailed_box(o, 0.20, 0.20)
    D = []

    def add(name, kind, detail, attrs, make):
        D.append((name, kind, detail, attrs, make))

    # Copies: the same picture, worse. Compression ladder at full size.
    add("jpeg-q100", "copy", "JPEG q100 4:4:4", (1, 100, 1, 1), lambda im, p: save_jpeg(im, p + ".jpg", 100, 0))
    add("jpeg-q95", "copy", "JPEG q95 4:4:4", (1, 95, 1, 1), lambda im, p: save_jpeg(im, p + ".jpg", 95, 0))
    for q in (90, 85, 75, 60, 45, 30):
        add(f"jpeg-q{q}", "copy", f"JPEG q{q} 4:2:0", (1, q, 1, 1), lambda im, p, q=q: save_jpeg(im, p + ".jpg", q))
    add("jpeg-q85-x3", "copy", "JPEG q85 4:2:0, re-encoded three times", (1, 85, 3, 1),
        lambda im, p: save_jpeg(im, p + ".jpg", 85, generations=3))
    for q in (90, 75, 50):
        add(f"webp-q{q}", "copy", f"WebP q{q}", (1, q, 1, 1),
            lambda im, p, q=q: rgb(im).save(p + ".webp", "WEBP", quality=q, method=6))
    add("avif-q60", "copy", "AVIF q60", (1, 60, 1, 1), lambda im, p: rgb(im).save(p + ".avif", "AVIF", quality=60))
    add("jxl-d1", "copy", "JPEG XL distance 1", (1, "jxl-d1", 1, 1), lambda im, p: jxl(im, p + ".jxl", 1))
    add("jxl-d4", "copy", "JPEG XL distance 4", (1, "jxl-d4", 1, 1), lambda im, p: jxl(im, p + ".jxl", 4))
    # Resolution ladder, lossless.
    for s in (90, 75, 50, 33, 25, 12):
        add(f"scale-{s}", "copy", f"{s} % Lanczos, PNG", (s / 100, 100, 1, 1), lambda im, p, s=s: png(resized(im, s / 100), p))
    add("scale-50-bilinear", "copy", "50 % bilinear, PNG", (0.5, 100, 1, 1), lambda im, p: png(resized(im, 0.5, Image.BILINEAR), p))
    add("scale-50-nearest", "copy", "50 % nearest neighbour, PNG", (0.5, 100, 1, 1), lambda im, p: png(resized(im, 0.5, Image.NEAREST), p))
    # Web copies: smaller and compressed.
    add("scale-50-jpeg-q85", "copy", "50 % Lanczos, JPEG q85 4:2:0", (0.5, 85, 1, 1), lambda im, p: save_jpeg(resized(im, 0.5), p + ".jpg", 85))
    add("scale-25-jpeg-q75", "copy", "25 % Lanczos, JPEG q75 4:2:0", (0.25, 75, 1, 1), lambda im, p: save_jpeg(resized(im, 0.25), p + ".jpg", 75))
    add("upscale-50-x2", "copy", "50 % Lanczos, then back to full size", (0.5, 100, 1, 1),
        lambda im, p: png(resized(resized(im, 0.5), 2.0).resize(im.size, Image.LANCZOS), p))
    # Processed copies.
    add("sharpen", "copy", "unsharp mask 1 px 80 %", (1, 100, 1, 1), lambda im, p: png(rgb(im).filter(ImageFilter.UnsharpMask(1, 80, 0)), p))
    add("blur", "copy", "Gaussian blur 1 px", (1, 100, 1, 1), lambda im, p: png(rgb(im).filter(ImageFilter.GaussianBlur(1)), p))
    add("brighter", "copy", "brightness +5 %", (1, 100, 1, 1), lambda im, p: png(ImageEnhance.Brightness(rgb(im)).enhance(1.05), p))
    add("saturated", "copy", "saturation +15 %", (1, 100, 1, 1), lambda im, p: png(ImageEnhance.Color(rgb(im)).enhance(1.15), p))
    # Crops: copy or version is the user's call.
    for c in (1, 2, 5, 10, 20):
        add(f"crop-{c}", "crop", f"{c} % cut from each side", (1, 100, 1, round((1 - c / 50) ** 2, 4)),
            lambda im, p, c=c: png(cropped(im, c / 100, c / 100, c / 100, c / 100), p))
    add("crop-right-10", "crop", "10 % cut from the right side only", (1, 100, 1, 0.9),
        lambda im, p: png(cropped(im, 0, 0, 0.10, 0), p))
    add("crop-square", "crop", "centre square", (1, 100, 1, round(min(o.size) / max(o.size), 4)),
        lambda im, p: png(centre_square(im), p))
    add("crop-5-rescaled", "crop", "5 % cut from each side, then resized back to full size", (1, 100, 1, 0.81),
        lambda im, p: png(cropped(im, 0.05, 0.05, 0.05, 0.05).resize(im.size, Image.LANCZOS), p))
    # Overlays: added around or on top.
    add("border-5", "overlay", "white border, 5 % of the long side", (1, 100, 1, 1), lambda im, p: png(padded(im, 0.05, (255, 255, 255)), p))
    add("watermark-corner", "overlay", "small semi-transparent text, bottom right", (1, 100, 1, 1),
        lambda im, p: png(text(im, "@reposter", 0.03, (0.70, 0.96), (255, 255, 255), 160), p))
    add("watermark-centre", "overlay", "large semi-transparent text across the middle", (1, 100, 1, 1),
        lambda im, p: png(text(im, "SAMPLE", 0.16, (0.5, 0.5), (255, 255, 255), 90), p))
    # Tone and geometry.
    add("gray", "gray", "greyscale (ITU-R 601 luma)", (1, 100, 1, 1), lambda im, p: png(im.convert("L").convert("RGB"), p))
    add("mirror", "transform", "mirrored left-right", (1, 100, 1, 1), lambda im, p: png(rgb(im).transpose(Image.FLIP_LEFT_RIGHT), p))
    add("rotate-90", "transform", "rotated 90 degrees", (1, 100, 1, 1), lambda im, p: png(rgb(im).transpose(Image.ROTATE_90), p))
    # Edits: versions, on the most detailed regions.
    add("sign", "edit", "small text near the bottom-left corner", (1, 100, 1, 1),
        lambda im, p: png(text(im, "sample signature", 0.025, (0.03, 0.94), (20, 20, 20)), p))
    add("bar", "edit", "black bar, 16 % x 3 % of the image", (1, 100, 1, 1),
        lambda im, p: png(bar(im, frac_box(im, detailed_box(im, 0.16, 0.03))), p))
    add("mosaic", "edit", "mosaic, 15 % x 15 % region, cells 1.5 % of the width", (1, 100, 1, 1),
        lambda im, p: png(mosaic(im, frac_box(im, detailed_box(im, 0.15, 0.15)), max(4, im.width * 15 // 1000)), p))
    add("smudge", "edit", "a 10 % x 10 % detailed region blurred away (4 % of the width)", (1, 100, 1, 1),
        lambda im, p: png(smudge(im, frac_box(im, detailed_box(im, 0.10, 0.10)), im.width * 0.04), p))
    add("clone", "edit", "a 12 % x 12 % detailed region copied over another one", (1, 100, 1, 1),
        lambda im, p: png(clone_patch(im, detailed_box(im, 0.12, 0.12), detailed_box(im, 0.12, 0.12, avoid=detailed_box(im, 0.12, 0.12))), p))
    add("recolour-local", "edit", "hue +90 degrees in a 20 % x 20 % region", (1, 100, 1, 1),
        lambda im, p: png(hue_shift(im, 90, frac_box(im, edit_area)), p))
    add("recolour-global", "edit", "hue +90 degrees everywhere", (1, 100, 1, 1), lambda im, p: png(hue_shift(im, 90), p))
    return D


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("config")
    ap.add_argument("set")
    ap.add_argument("--rebuild", action="store_true")
    a = ap.parse_args()
    config = json.load(open(a.config, encoding="utf-8"))
    archive = config["archive"]
    os.makedirs(a.set, exist_ok=True)
    for case in config["cases"]:
        folder = os.path.join(a.set, case["name"])
        os.makedirs(folder, exist_ok=True)
        rows = []

        def copy(rel, name, kind, detail):
            src, dst = os.path.join(archive, rel), os.path.join(folder, name)
            if a.rebuild or not os.path.exists(dst) or os.path.getsize(dst) != os.path.getsize(src):
                shutil.copyfile(src, dst)
            rows.append([name, kind, detail, rel, "", "", "", ""])

        ext = case["original"].rsplit(".", 1)[1].lower()
        copy(case["original"], f"original.{ext}", "original", "the artist's final image")
        for i, rel in enumerate(case.get("variants", []), 1):
            copy(rel, f"variant-{i:02d}.{rel.rsplit('.', 1)[1].lower()}", "variant", "the artist's other version " + str(i))
        steps = case.get("steps", [])
        for i, rel in enumerate(steps, 1):
            copy(rel, f"step-{i:02d}.{rel.rsplit('.', 1)[1].lower()}", "step", f"step {i} of {len(steps)}")
        original = Image.open(os.path.join(folder, f"original.{ext}"))
        original.load()
        for name, kind, detail, (scale, quality, generations, kept), make in derived(original):
            made = [f for f in os.listdir(folder) if f.rsplit(".", 1)[0] == name]
            if a.rebuild or not made:
                for f in made:
                    os.remove(os.path.join(folder, f))
                make(original, os.path.join(folder, name))
                made = [f for f in os.listdir(folder) if f.rsplit(".", 1)[0] == name]
            rows.append([made[0], kind, detail, f"original.{ext}", str(scale), str(quality), str(generations), str(kept)])
        with open(os.path.join(folder, "manifest.tsv"), "w", encoding="utf-8", newline="\n") as f:
            f.write("\t".join(FIELDS) + "\n")
            for r in rows:
                f.write("\t".join(r) + "\n")
        print(f"{case['name']}: {len(rows)} images", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
