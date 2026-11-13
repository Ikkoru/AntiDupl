"""Images with transparency compared as shown (T48): makes the test pairs,
one folder per case, runs each through a build's core with mean square,
SSIM and local colour, with transparency shown and ignored, and prints
PASS or FAIL per case and setting against what it should give.

  hidden-colour        same picture, white under the transparency in one file,
                       black in the other: a pair (pixel-identical: 0.00)
  hidden-mirrored      the same, one mirrored: a pair, found as a mirror
                       (--transformed: the over-black thumbnails turn too)
  flattened-white      transparent picture and a JPEG of it over white: a pair
  flattened-black      the same over black: a pair
  flattened-busy       the same over a patterned background: no pair
  white-lines          two different white drawings on transparency: no pair
  white-lines-blank    a white drawing on transparency and a plain white JPEG:
                       no pair (filled with white it would be blank)
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
# case: (pair with transparency shown, pair with it ignored)
EXPECTED = {
    "hidden-colour": (True, False),
    "hidden-mirrored": (True, False),
    "flattened-white": (True, False),
    "flattened-black": (True, False),
    "flattened-busy": (False, False),
    "white-lines": (False, True),
    "white-lines-blank": (False, True),
    "bmp-unused-alpha": (True, True),
}
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
            for shown in (True, False):
                user = os.path.join(out, "users", f"{case}-{number}-{int(shown)}")
                os.makedirs(user)
                r = subprocess.run([sys.executable, TOOL, dll, user, os.path.join(out, "cases", case),
                                    "--algorithm", number, "--threshold", threshold, "--any-ratio", "--transformed",
                                    *extra, *([] if shown else ["--alpha-ignored"])], capture_output=True, text=True)
                if r.returncode:
                    sys.exit(r.stderr)
                pair = re.match(r"\S+  shows", r.stdout) is not None
                want = expected[0 if shown else 1]
                ok = pair == want
                failures += not ok
                print(f"{'PASS' if ok else 'FAIL'}  {case:18} {algorithm:13} {'shown' if shown else 'ignored':8}"
                      f"{'pair' if pair else 'no pair':8} (should be {'pair' if want else 'no pair'})")
    print("all passed" if not failures else f"{failures} FAILED")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
