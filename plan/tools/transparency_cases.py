"""Images with transparency compared as shown (T48): makes the test pairs,
one folder per case, runs each through a build's core with mean square,
SSIM and local colour in three settings, and prints PASS or FAIL per case
and setting against what it should give. The settings: transparency shown
("Improve transparent image comparison"), ignored (the option off), and
masked (shown, plus "Ignore areas with transparency in both images").

  hidden-colour        same picture, white under the transparency in one file,
                       black in the other: a pair (pixel-identical: 0.00)
  hidden-mirrored      the same, one mirrored: a pair, found as a mirror
                       (--transformed: the over-black thumbnails turn too)
  flattened-white      transparent picture and a JPEG of it over white: a pair
  flattened-black      the same over black: a pair
  flattened-busy       the same over a patterned background: a pair only
                       masked
  flattened-picture    the same laid over another picture: a pair only masked
  different-on-busy    another drawing over the pattern: no pair
  extra-shapes         the drawing on transparency, and the same with more
                       shapes added where it was transparent: a pair only
                       masked (compared where both are opaque)
  disjoint             two drawings on transparency, one on the left half and
                       one on the right: no pair (masked, too small an area)
  shared-strip         one dense picture cut to its left three fifths and to
                       its right three fifths: no pair (masked, the identical
                       middle strip is too little of either)
  white-lines          two different white drawings on transparency: no pair
  white-lines-blank    a white drawing on transparency and a plain white JPEG:
                       no pair (filled with white it would be blank; masked,
                       the drawing is one colour)
  bmp-unused-alpha     a 32-bit BMP whose fourth byte is 0 everywhere, and the
                       same picture as a 24-bit PNG: a pair (the BMP is opaque)

Ignored, the colour under transparent pixels counts as it did before the
option: the white drawings pair (both plain white), the hidden colours and
the flattened copies don't.

    py -3 transparency_cases.py <bin\\Release> <new scratch folder> [--butteraugli]

--butteraugli adds Butteraugli and the aligned search, at 12 and 768 px,
for builds that have them (the personal branch).
"""
import os
import re
import struct
import subprocess
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageOps

W, H = 640, 480
TOOL = os.path.join(os.path.dirname(os.path.abspath(__file__)), "core_search.py")
SETTINGS = ("shown", "ignored", "masked")
# case: pair or not in each of SETTINGS
EXPECTED = {
    "hidden-colour": (True, False, True),
    "hidden-mirrored": (True, False, True),
    "flattened-white": (True, False, True),
    "flattened-black": (True, False, True),
    "flattened-busy": (False, False, True),
    "flattened-picture": (False, False, True),
    "different-on-busy": (False, False, False),
    "extra-shapes": (False, False, True),
    "disjoint": (False, False, False),
    # Ignored, it pairs: the cut zeroes alpha only, so the whole picture is
    # still stored under the transparent pixels.
    "shared-strip": (False, True, False),
    "white-lines": (False, True, False),
    "white-lines-blank": (False, True, False),
    "bmp-unused-alpha": (True, True, True),
}
# Searched without turns and mirrors: turned 180 degrees the two halves
# do overlap, and two different drawings then pass the loose thresholds
# below, which tests nothing of the overlap rule.
UNTURNED = {"disjoint", "shared-strip"}
ALGORITHMS = [("mean square", "0", "20"), ("SSIM", "1", "30"), ("local colour", "3", "30")]
# With --butteraugli, for builds that have them: at their default at 768 px.
BUTTERAUGLI = [("Butteraugli", "4", "12"), ("aligned", "5", "12")]


def art(seed):
    """A picture on transparency: shapes and lines, alpha 0 around them."""
    rng = np.random.default_rng(seed)
    im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    for _ in range(12):
        x, y = rng.integers(40, W - 120), rng.integers(40, H - 120)
        c = tuple(int(v) for v in rng.integers(30, 230, 3)) + (255,)
        d.ellipse([x, y, x + rng.integers(40, 110), y + rng.integers(40, 110)], fill=c, outline=(20, 20, 20, 255), width=3)
    for _ in range(6):
        d.line([tuple(rng.integers(0, W, 2)), tuple(rng.integers(0, H, 2))], fill=(10, 10, 10, 255), width=4)
    return im


def with_hidden(im, rgb):
    """The same picture with rgb stored under fully transparent pixels."""
    a = np.asarray(im).copy()
    a[a[..., 3] == 0, :3] = rgb
    return Image.fromarray(a, "RGBA")


def white_lines(seed):
    """White on transparency, bold enough that whole thumbnail pixels are
    opaque: the case TImageComparer::UniformFill's contrast test is for."""
    rng = np.random.default_rng(seed)
    im = Image.new("RGBA", (W, H), (255, 255, 255, 0))
    d = ImageDraw.Draw(im)
    for _ in range(10):
        d.line([tuple(rng.integers(0, W, 2)), tuple(rng.integers(0, H, 2))], fill=(255, 255, 255, 255), width=28)
    for _ in range(4):
        x, y = rng.integers(0, W - 120), rng.integers(0, H - 120)
        d.ellipse([x, y, x + 110, y + 110], fill=(255, 255, 255, 255))
    return im


def over(im, background):
    bg = background.convert("RGBA") if isinstance(background, Image.Image) else Image.new("RGBA", im.size, background)
    return Image.alpha_composite(bg, im).convert("RGB")


def make(out):
    def case(name, files):
        d = os.path.join(out, name)
        os.makedirs(d, exist_ok=True)
        for fname, im, kw in files:
            im.save(os.path.join(d, fname), **kw)

    a = art(1)
    busy = Image.fromarray((np.indices((H, W)).sum(axis=0) % 24 < 12).astype(np.uint8)[..., None].repeat(3, 2) * 200 + 30)
    case("hidden-colour", [("a.png", with_hidden(a, (255, 255, 255)), {}), ("b.png", with_hidden(a, (0, 0, 0)), {})])
    case("hidden-mirrored", [("a.png", with_hidden(a, (255, 255, 255)), {}),
                             ("b.png", ImageOps.mirror(with_hidden(a, (0, 0, 0))), {})])
    case("flattened-white", [("a.png", with_hidden(a, (0, 0, 0)), {}), ("b.jpg", over(a, (255, 255, 255)), {"quality": 92})])
    case("flattened-black", [("a.png", with_hidden(a, (255, 255, 255)), {}), ("b.jpg", over(a, (0, 0, 0)), {"quality": 92})])
    case("flattened-busy", [("a.png", a, {}), ("b.jpg", over(a, busy), {"quality": 92})])
    scene = over(art(5), Image.fromarray(np.tile(np.linspace(60, 200, W, dtype=np.uint8), (H, 1))).convert("RGB"))
    case("flattened-picture", [("a.png", a, {}), ("b.jpg", over(a, scene), {"quality": 92})])
    case("different-on-busy", [("a.png", a, {}), ("b.jpg", over(art(4), busy), {"quality": 92})])
    case("extra-shapes", [("a.png", a, {}), ("b.png", Image.alpha_composite(art(6), a), {})])

    def half(im, keep_left):
        arr = np.asarray(im).copy()
        if keep_left:
            arr[:, W // 2:, 3] = 0
        else:
            arr[:, :W // 2, 3] = 0
        return Image.fromarray(arr, "RGBA")
    case("disjoint", [("a.png", half(a, True), {}), ("b.png", half(art(7), False), {})])

    def keep(im, x0, x1):
        arr = np.asarray(im).copy()
        arr[:, :x0, 3] = 0
        arr[:, x1:, 3] = 0
        return Image.fromarray(arr, "RGBA")
    # A dense picture, opaque everywhere: the strip is a large area, which
    # the area limit lets through, and a third of either picture.
    tiles = np.random.default_rng(8).integers(20, 236, (H // 40, W // 40, 3), dtype=np.uint8)
    mosaic = Image.fromarray(np.dstack([tiles.repeat(40, 0).repeat(40, 1), np.full((H, W), 255, np.uint8)]), "RGBA")
    case("shared-strip", [("a.png", keep(mosaic, 0, W * 3 // 5), {}), ("b.png", keep(mosaic, W * 2 // 5, W), {})])
    case("white-lines", [("a.png", white_lines(2), {}), ("b.png", white_lines(3), {})])
    case("white-lines-blank", [("a.png", white_lines(2), {}),
                               ("b.jpg", Image.new("RGB", (W, H), (255, 255, 255)), {"quality": 92})])
    # 32-bit BI_RGB BMP, bottom-up, fourth byte 0: the picture over white.
    flat = np.asarray(over(a, (255, 255, 255)))
    d = os.path.join(out, "bmp-unused-alpha")
    os.makedirs(d, exist_ok=True)
    rows = b"".join(np.concatenate([flat[y, :, ::-1], np.zeros((W, 1), np.uint8)], axis=1).tobytes()
                    for y in range(H - 1, -1, -1))
    header = struct.pack("<2sIHHI", b"BM", 54 + len(rows), 0, 0, 54) + \
        struct.pack("<IiiHHIIiiII", 40, W, H, 1, 32, 0, len(rows), 2835, 2835, 0, 0)
    open(os.path.join(d, "a.bmp"), "wb").write(header + rows)
    Image.fromarray(flat).save(os.path.join(d, "b.png"))


def main():
    dll, out = sys.argv[1], sys.argv[2]
    algorithms = ALGORITHMS + (BUTTERAUGLI if "--butteraugli" in sys.argv[3:] else [])
    if os.path.exists(out):
        sys.exit("give a folder that doesn't exist yet")
    make(os.path.join(out, "cases"))
    failures = 0
    for case, expected in EXPECTED.items():
        for algorithm, number, threshold in algorithms:
            extra = ["--butteraugli-size", "768"] if number in ("4", "5") else []
            for setting, want in zip(SETTINGS, expected):
                user = os.path.join(out, "users", f"{case}-{number}-{setting}")
                os.makedirs(user)
                flags = {"shown": [], "ignored": ["--alpha-ignored"], "masked": ["--ignore-transparent"]}[setting]
                r = subprocess.run([sys.executable, TOOL, dll, user, os.path.join(out, "cases", case),
                                    "--algorithm", number, "--threshold", threshold, "--any-ratio",
                                    *([] if case in UNTURNED else ["--transformed"]),
                                    *extra, *flags], capture_output=True, text=True)
                if r.returncode:
                    sys.exit(r.stderr)
                pair = re.match(r"\S+  shows", r.stdout) is not None
                ok = pair == want
                failures += not ok
                print(f"{'PASS' if ok else 'FAIL'}  {case:18} {algorithm:13} {setting:8}"
                      f"{'pair' if pair else 'no pair':8} (should be {'pair' if want else 'no pair'})")
    print("all passed" if not failures else f"{failures} FAILED")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
