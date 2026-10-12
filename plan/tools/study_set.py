"""Builds the image set of the settings study (plan 07): for each artwork
in the config, copies its original, the artist's variants and the step
pictures out of the archive (read only), and derives copies and edits of
the original.

Usage: py -3 study_set.py <config .json> <output folder>

The config names files in the user's archive, so it is kept outside this
repository (on the user's PC: the workspace's Research\study_set.json):
    {"archive": "<folder>", "artworks": [{"name", "original",
     "variants" (a pattern with {}), "variant_ids", "steps", "step_ids"}]}

Output, one folder per artwork:
    original.png             the artist's final image
    variant-<id>.png         the artist's other versions
    step-<id>.<ext>          work-in-progress steps, sketch first
    <derived>.<ext>          made from original.png, see DERIVED
and manifest.tsv (file, artwork, kind, detail, origin). The folder gets a
CACHEDIR.TAG: everything in it is rebuilt by running this again.
"""
import argparse
import json
import os
import shutil
import sys

from PIL import Image, ImageDraw, ImageFont

TAG = "Signature: 8a477f597d28d172789f06886806bc55\n# Settings study image set: rebuilt by plan/tools/study_set.py\n"


def save_jpeg(im, path, quality, subsampling):
    im.convert("RGB").save(path, "JPEG", quality=quality, subsampling=subsampling, optimize=True)


def resized(im, factor):
    return im.resize((max(1, round(im.width * factor)), max(1, round(im.height * factor))), Image.LANCZOS)


def box(im, x0, y0, x1, y1):
    return (round(im.width * x0), round(im.height * y0), round(im.width * x1), round(im.height * y1))


def detailed_box(im, w, h):
    """The w x h (fractions of the image) region with the most detail
    (sum of gradient magnitudes on a 256 px copy), so an edit lands where
    it changes something."""
    import numpy as np
    g = np.asarray(im.convert("L").resize((256, round(256 * im.height / im.width)), Image.BOX), dtype=np.float64)
    energy = np.abs(np.diff(g, axis=0))[:, :-1] + np.abs(np.diff(g, axis=1))[:-1, :]
    integral = np.pad(energy.cumsum(0).cumsum(1), ((1, 0), (1, 0)))
    bh, bw = max(1, round(h * energy.shape[0])), max(1, round(w * energy.shape[1]))
    sums = integral[bh:, bw:] - integral[:-bh, bw:] - integral[bh:, :-bw] + integral[:-bh, :-bw]
    y, x = np.unravel_index(np.argmax(sums), sums.shape)
    fx, fy = x / energy.shape[1], y / energy.shape[0]
    return box(im, fx, fy, fx + w, fy + h)


def mosaic(im, region, cell):
    out = im.copy()
    part = out.crop(region)
    small = part.resize((max(1, part.width // cell), max(1, part.height // cell)), Image.BOX)
    out.paste(small.resize(part.size, Image.NEAREST), region[:2])
    return out


def hue_shift(im, degrees, region=None):
    out = im.convert("RGB")
    part = out.crop(region) if region else out
    h, s, v = part.convert("HSV").split()
    shift = round(degrees / 360 * 256)
    h = h.point(lambda x: (x + shift) % 256)
    shifted = Image.merge("HSV", (h, s, v)).convert("RGB")
    if region:
        out.paste(shifted, region[:2])
        return out
    return shifted


def signed(im):
    out = im.convert("RGB")
    draw = ImageDraw.Draw(out)
    size = max(12, im.width // 40)
    font = ImageFont.load_default(size=size)
    draw.text((round(im.width * 0.03), round(im.height * 0.95) - size), "sample signature", fill=(20, 20, 20), font=font)
    return out


def barred(im):
    out = im.convert("RGB")
    ImageDraw.Draw(out).rectangle(detailed_box(im, 0.16, 0.03), fill=(0, 0, 0))
    return out


def cropped(im, fraction):
    return im.crop(box(im, fraction, fraction, 1 - fraction, 1 - fraction))


# name, kind, detail, how to make it from the original
DERIVED = [
    ("jpeg-q95", "copy", "JPEG q95 4:4:4", lambda im, p: save_jpeg(im, p + ".jpg", 95, 0)),
    ("jpeg-q80", "copy", "JPEG q80 4:2:0", lambda im, p: save_jpeg(im, p + ".jpg", 80, 2)),
    ("jpeg-q50", "copy", "JPEG q50 4:2:0", lambda im, p: save_jpeg(im, p + ".jpg", 50, 2)),
    ("webp-q80", "copy", "WebP q80", lambda im, p: im.convert("RGB").save(p + ".webp", "WEBP", quality=80, method=6)),
    ("resize-75", "copy", "75 % Lanczos, PNG", lambda im, p: resized(im, 0.75).save(p + ".png")),
    ("resize-50-jpeg-q85", "copy", "50 % Lanczos, JPEG q85 4:2:0", lambda im, p: save_jpeg(resized(im, 0.5), p + ".jpg", 85, 2)),
    ("resize-25", "copy", "25 % Lanczos, PNG", lambda im, p: resized(im, 0.25).save(p + ".png")),
    ("gray", "gray", "greyscale (ITU-R 601 luma)", lambda im, p: im.convert("L").convert("RGB").save(p + ".png")),
    ("crop-1", "crop", "1 % cut from each side", lambda im, p: cropped(im, 0.01).save(p + ".png")),
    ("crop-5", "crop", "5 % cut from each side", lambda im, p: cropped(im, 0.05).save(p + ".png")),
    ("sign", "edit", "small text near the bottom-left corner", lambda im, p: signed(im).save(p + ".png")),
    # The edits below go on the most detailed region of their size.
    ("bar", "edit", "black bar, 16 % x 3 % of the image", lambda im, p: barred(im).save(p + ".png")),
    ("mosaic", "edit", "mosaic, 15 % x 15 % region, cells 1.5 % of the width",
     lambda im, p: mosaic(im.convert("RGB"), detailed_box(im, 0.15, 0.15), max(4, im.width * 15 // 1000)).save(p + ".png")),
    ("recolour-local", "edit", "hue +90 degrees in a 20 % x 20 % region",
     lambda im, p: hue_shift(im, 90, detailed_box(im, 0.20, 0.20)).save(p + ".png")),
    ("recolour-global", "edit", "hue +90 degrees everywhere", lambda im, p: hue_shift(im, 90).save(p + ".png")),
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("config")
    ap.add_argument("out")
    a = ap.parse_args()
    config = json.load(open(a.config, encoding="utf-8"))
    archive = config["archive"]
    os.makedirs(a.out, exist_ok=True)
    with open(os.path.join(a.out, "CACHEDIR.TAG"), "w", encoding="ascii", newline="\n") as f:
        f.write(TAG)
    rows = []
    for art in config["artworks"]:
        folder = os.path.join(a.out, art["name"])
        os.makedirs(folder, exist_ok=True)

        def copy(rel, name, kind, detail):
            src = os.path.join(archive, rel)
            dst = os.path.join(folder, name)
            if not os.path.exists(dst) or os.path.getsize(dst) != os.path.getsize(src):
                shutil.copyfile(src, dst)
            rows.append((name, art["name"], kind, detail, rel))

        copy(art["original"], "original.png", "original", "the artist's final image")
        for vid in art.get("variant_ids", []):
            copy(art["variants"].format(vid), f"variant-{vid}.png", "variant", "the artist's version " + vid)
        steps = art.get("step_ids", [])
        for i, sid in enumerate(steps):
            ext = sid.rsplit(".", 1)[1]
            copy(art["steps"].format(sid), f"step-{sid.rsplit('.', 1)[0]}.{ext}", "step", f"step {i + 1} of {len(steps)}")
        original = Image.open(os.path.join(folder, "original.png"))
        original.load()
        for name, kind, detail, make in DERIVED:
            base = os.path.join(folder, name)
            make(original, base)
            made = [f for f in os.listdir(folder) if f.rsplit(".", 1)[0] == name]
            rows.append((made[0], art["name"], kind, detail, "original.png"))
        print(f"{art['name']}: {sum(1 for r in rows if r[1] == art['name'])} images", flush=True)
    with open(os.path.join(a.out, "manifest.tsv"), "w", encoding="utf-8", newline="\n") as f:
        f.write("file\tartwork\tkind\tdetail\torigin\n")
        for r in rows:
            f.write("\t".join(r) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
