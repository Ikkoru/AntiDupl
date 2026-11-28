"""Upscale tests on made pairs (T37): a smaller copy s of each study
original against a larger X that is either the genuine larger reduction of
the original or s blown up by a known kernel (nearest, bilinear, bicubic,
Mitchell, Lanczos, Lanczos then sharpened), as PNG or saved again as JPEG
q90 and q75; factors 1.25 to 4, the larger 1536 px on its longest side.
Detectors:
  line_detail      study_metrics.line_detail (under UPSCALED_LINE_DETAIL
                   = blown up)
  resdet_at_small  resdet on X alone, asked one question: its confidence in
                   a detection within 2 % of s's width or height (0 = none)
  resdet_any       its highest confidence in any detection
Writes a TSV; --summary prints the medians and the hits.

With --ai, the larger copies are AI upscales instead: each original
reduced to 384 px on its shorter side, blown up 2x and 4x by waifu2x
(CUNet, noise 0 and 1), Real-ESRGAN (x4plus-anime at 4x, animevideov3)
and Real-CUGAN (se, no denoising), the ncnn-vulkan builds as Waifu2x-
Extension-GUI ships them (its program folder, holding one folder per
upscaler); the genuine reduction to the same size alongside; as PNG and
q90. They run on the GPU.

    py -3 upscale_grid.py <set> <work folder> <out.tsv> --resdet <resdet.exe>
    py -3 upscale_grid.py <set> <work folder> <out.tsv> --resdet <resdet.exe> --ai <folder>
    py -3 upscale_grid.py --summary <out.tsv>

ImageMagick (`magick`) makes the Mitchell copies; OpenCV (STUDY_PYLIB) lets
line_detail cut a pair to what both show.
"""
import argparse
import csv
import os
import statistics
import subprocess
import sys

from PIL import Image, ImageFilter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import study_metrics as sm  # noqa: E402

Image.MAX_IMAGE_PIXELS = None
FACTORS = (1.25, 1.5, 2, 3, 4)
LARGE = 1536
KERNELS = {"nearest": Image.Resampling.NEAREST, "bilinear": Image.Resampling.BILINEAR,
           "bicubic": Image.Resampling.BICUBIC, "lanczos": Image.Resampling.LANCZOS}
KINDS = ["genuine", "nearest", "bilinear", "bicubic", "mitchell", "lanczos", "lanczos+sharpen"]
def study_cases(set_dir):
    """The set's illustration cases: the folders with a manifest and an
    original (the photo and hand-added folders have neither)."""
    return sorted(d for d in os.listdir(set_dir)
                  if os.path.isfile(os.path.join(set_dir, d, "manifest.tsv"))
                  and os.path.isfile(os.path.join(set_dir, d, "original.png")))


COLS = ["case", "factor", "kind", "post", "line_detail", "resdet_at_small", "resdet_any"]


def resdet(exe, path, size, tol=0.02):
    """(confidence of a detection within tol of size's width or height,
    highest confidence of any detection); 0 when there is none."""
    r = subprocess.run([exe, "-v", "3", path], capture_output=True, text=True)
    at, best = 0.0, 0.0
    for axis, line in enumerate(r.stdout.strip().splitlines()[:2]):
        for tok in line.split():
            v, c = tok.split(":")
            c = float(c)
            if c <= 0:
                continue
            best = max(best, c)
            if abs(int(v) - size[axis]) <= tol * size[axis]:
                at = max(at, c)
    return at, best


def measure(a):
    os.makedirs(a.work, exist_ok=True)
    with open(a.out, "w", encoding="utf-8", newline="") as out:
        out.write("\t".join(COLS) + "\n")
        for case in study_cases(a.set):
            orig = Image.open(os.path.join(a.set, case, "original.png")).convert("RGB")
            k = LARGE / max(orig.size)
            lsize = (round(orig.width * k), round(orig.height * k))
            genuine = orig.resize(lsize, Image.Resampling.BOX)
            for factor in FACTORS:
                ssize = (round(lsize[0] / factor), round(lsize[1] / factor))
                small = orig.resize(ssize, Image.Resampling.BOX)
                spath = os.path.join(a.work, f"{case}-{factor}-small.png")
                small.save(spath)
                larges = {"genuine": genuine}
                for name, kern in KERNELS.items():
                    larges[name] = small.resize(lsize, kern)
                mpath = os.path.join(a.work, f"{case}-{factor}-mitchell.png")
                subprocess.run(["magick", spath, "-filter", "Mitchell", "-resize", f"{lsize[0]}x{lsize[1]}!", mpath],
                               check=True)
                larges["mitchell"] = Image.open(mpath).convert("RGB")
                larges["lanczos+sharpen"] = larges["lanczos"].filter(ImageFilter.UnsharpMask(radius=2, percent=120, threshold=0))
                for kind in KINDS:
                    for post in ("png", "q90", "q75"):
                        xpath = os.path.join(a.work, f"{case}-{factor}-{kind}-{post}" + (".png" if post == "png" else ".jpg"))
                        if post == "png":
                            larges[kind].save(xpath)
                        else:
                            larges[kind].save(xpath, quality=int(post[1:]))
                        at, best = resdet(a.resdet, xpath, ssize)
                        row = [case, factor, kind, post, sm.line_detail(spath, xpath), at, best]
                        out.write("\t".join(str(v) for v in row) + "\n")
                        out.flush()
                        print(*row, flush=True)


def ai_upscalers(folder):
    """name -> (factors, function(input, output, factor))."""
    def tool(sub, exe, *args):
        def run(i, o, s):
            subprocess.run([os.path.join(folder, sub, exe), "-i", i, "-o", o, "-s", str(s), *args],
                           cwd=os.path.join(folder, sub), check=True, capture_output=True)
        return run
    return {
        "waifu2x-cunet-n0": ((2, 4), tool("waifu2x-ncnn-vulkan", "waifu2x-ncnn-vulkan_waifu2xEX.exe", "-n", "0", "-m", "models-cunet")),
        "waifu2x-cunet-n1": ((2, 4), tool("waifu2x-ncnn-vulkan", "waifu2x-ncnn-vulkan_waifu2xEX.exe", "-n", "1", "-m", "models-cunet")),
        "realesrgan-x4plus-anime": ((4,), tool("realesrgan-ncnn-vulkan", "realesrgan-ncnn-vulkan_waifu2xEX.exe", "-n", "realesrgan-x4plus-anime")),
        "realesr-animevideov3": ((2, 4), tool("realesrgan-ncnn-vulkan", "realesrgan-ncnn-vulkan_waifu2xEX.exe", "-n", "realesr-animevideov3")),
        "realcugan-se": ((2, 4), tool("realcugan-ncnn-vulkan", "realcugan-ncnn-vulkan_W2xEX.exe", "-n", "-1", "-m", "models-se")),
    }


def measure_ai(a):
    os.makedirs(a.work, exist_ok=True)
    upscalers = ai_upscalers(a.ai)
    with open(a.out, "w", encoding="utf-8", newline="") as out:
        out.write("\t".join(COLS) + "\n")
        for case in study_cases(a.set):
            orig = Image.open(os.path.join(a.set, case, "original.png")).convert("RGB")
            k = 384 / min(orig.size)
            ssize = (round(orig.width * k), round(orig.height * k))
            small = orig.resize(ssize, Image.Resampling.BOX)
            spath = os.path.join(a.work, f"{case}-small384.png")
            small.save(spath)
            for factor in (2, 4):
                lsize = (ssize[0] * factor, ssize[1] * factor)
                larges = {"genuine": orig.resize(lsize, Image.Resampling.BOX)}
                for name, (factors, run) in upscalers.items():
                    if factor in factors:
                        raw = os.path.join(a.work, f"{case}-ai{factor}-{name}-raw.png")
                        run(spath, raw, factor)
                        larges[name] = Image.open(raw).convert("RGB")
                for kind, X in larges.items():
                    for post in ("png", "q90"):
                        xpath = os.path.join(a.work, f"{case}-ai{factor}-{kind}-{post}" + (".png" if post == "png" else ".jpg"))
                        if post == "png":
                            X.save(xpath)
                        else:
                            X.save(xpath, quality=90)
                        at, best = resdet(a.resdet, xpath, ssize)
                        row = [case, factor, kind, post, sm.line_detail(spath, xpath), at, best]
                        out.write("\t".join(str(v) for v in row) + "\n")
                        out.flush()
                        print(*row, flush=True)


def summary(path):
    with open(path, encoding="utf-8") as f:
        rows = list(csv.DictReader(f, delimiter="\t"))
    # The kinds, factors and saves the file holds (the kernel grid's or --ai's).
    kinds = list(dict.fromkeys(r["kind"] for r in rows))
    factors = sorted({float(r["factor"]) for r in rows})
    posts = list(dict.fromkeys(r["post"] for r in rows))
    for det in ("line_detail", "resdet_at_small"):
        print(f"{det}: median over the pictures, factors {'/'.join(f'{f:g}' for f in factors)}; {', '.join(posts)}")
        for kind in kinds:
            cells = []
            for post in posts:
                cells.append("/".join(
                    (f"{statistics.median(v):.2f}" if v else "-") for v in
                    ([float(r[det]) for r in rows if r['kind'] == kind and r['post'] == post and float(r['factor']) == f]
                     for f in factors)))
            print(f"  {kind:24s} " + "  ".join(cells))
    gen = [r for r in rows if r["kind"] == "genuine"]
    up = [r for r in rows if r["kind"] != "genuine"]
    flag = lambda r: float(r["line_detail"]) < sm.UPSCALED_LINE_DETAIL
    print(f"genuine {len(gen)}: line_detail flags {sum(map(flag, gen))}, resdet names the smaller's size in "
          f"{sum(float(r['resdet_at_small']) > 0 for r in gen)}, resdet detects anything in {sum(float(r['resdet_any']) > 0 for r in gen)}")
    print(f"upscales {len(up)}: line_detail flags {sum(map(flag, up))}, resdet names the smaller's size in "
          f"{sum(float(r['resdet_at_small']) > 0 for r in up)}, either in {sum(flag(r) or float(r['resdet_at_small']) > 0 for r in up)}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("set", nargs="?")
    ap.add_argument("work", nargs="?")
    ap.add_argument("out", nargs="?")
    ap.add_argument("--resdet")
    ap.add_argument("--summary")
    ap.add_argument("--ai")
    a = ap.parse_args()
    if a.summary:
        summary(a.summary)
    else:
        measure_ai(a) if a.ai else measure(a)


if __name__ == "__main__":
    main()
