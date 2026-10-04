"""Which difference metric separates "worse copy" duplicates from real variants?

Usage:
    python metric_experiment.py source1.jpg [source2.png ...] [--maxside 1024] [--out results.json]

For every source image it synthesises:
  dup:  JPEG re-saves (q95..q40), WebP q80, 50 % / 25 % downscales      -> should look SAME
  var:  hue-rotated colour variant (same luma), local recolour, white box, face-size edit,
        signature bar, mosaic censor, small red text                     -> should look DIFFERENT
  geo:  1 % / 3 % border crops resized back                               -> ambiguous
and prints per-metric ranges plus whether duplicates and variants separate.

Always computed (pip install -r requirements.txt):
  AntiDupl SSIM (current formula, correct decode), proposed colour worst-block metric,
  perceptual hashes (imagehash), windowed colour SSIM (scikit-image), SSIMULACRA2 (py port —
  NOTE: disagrees with the reference on downscaled images, prefer the native tools below).
Optional native tools, looked up in --tool-dir / %ANTIDUPL_TOOL_DIRS% first, then PATH:
  ssimulacra2, butteraugli_main  libjxl reference tools (Windows: jxl-x64-windows-static.zip from
                                 github.com/libjxl/libjxl/releases, its bin folder)
  butteraugli     (cargo install butteraugli-cli)   -> pure-Rust Butteraugli, max-norm and 3-norm
  ssimulacra2_rs  (cargo install ssimulacra2_rs --no-default-features)
  dssim           (cargo install dssim)
  bh              (butteraugli_harness, google/butteraugli C++; see README) -> 512 px timing
"""
import argparse, io, json, os, shutil, subprocess, struct, tempfile, time
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from adsim import reduced, gray_correct, antidupl_ssim_difference

try:
    import imagehash
except ImportError:
    imagehash = None
try:
    from skimage.metrics import structural_similarity
except ImportError:
    structural_similarity = None
try:
    from ssimulacra2 import compute_ssimulacra2
except ImportError:
    compute_ssimulacra2 = None


def jpeg(rgb, q):
    b = io.BytesIO(); Image.fromarray(rgb).save(b, "JPEG", quality=q); b.seek(0)
    return np.asarray(Image.open(b).convert("RGB"))


def webp(rgb, q):
    b = io.BytesIO(); Image.fromarray(rgb).save(b, "WEBP", quality=q); b.seek(0)
    return np.asarray(Image.open(b).convert("RGB"))


def to_ycc(x):
    x = x.astype(np.float64)
    return (0.299 * x[..., 0] + 0.587 * x[..., 1] + 0.114 * x[..., 2],
            -0.168736 * x[..., 0] - 0.331264 * x[..., 1] + 0.5 * x[..., 2],
            0.5 * x[..., 0] - 0.418688 * x[..., 1] - 0.081312 * x[..., 2])


def from_ycc(y, cb, cr):
    return np.clip(np.stack([y + 1.402 * cr, y - 0.344136 * cb - 0.714136 * cr, y + 1.772 * cb], -1) + 0.5, 0, 255).astype(np.uint8)


def variants(src):
    H, W, _ = src.shape
    v = {f"dup: jpeg q{q}": jpeg(src, q) for q in (95, 85, 75, 60, 40)}
    v["dup: webp q80"] = webp(src, 80)
    v["dup: resize 50% + q90"] = jpeg(np.asarray(Image.fromarray(src).resize((W // 2, H // 2), Image.LANCZOS)), 90)
    v["dup: resize 25% + q90"] = jpeg(np.asarray(Image.fromarray(src).resize((W // 4, H // 4), Image.LANCZOS)), 90)
    y, cb, cr = to_ycc(src); a = np.deg2rad(120)
    v["var: hue +120 (same luma)"] = from_ycc(y, cb * np.cos(a) - cr * np.sin(a), cb * np.sin(a) + cr * np.cos(a))
    x = src.copy(); s = (slice(int(.05 * H), int(.25 * H)), slice(int(.44 * W), int(.70 * W))); x[s] = x[s][..., [2, 1, 0]]
    v["var: local recolour 5%"] = x
    x = src.copy(); x[int(.7 * H):int(.84 * H), int(.05 * W):int(.19 * W)] = 255
    v["var: white box 2%"] = x
    x = src.copy(); s = (slice(int(.24 * H), int(.36 * H)), slice(int(.44 * W), int(.56 * W))); x[s] = x[s][:, ::-1]
    v["var: face-size edit 1.5%"] = x
    x = src.copy(); x[int(.93 * H):int(.95 * H), int(.80 * W):int(.97 * W)] = 20
    v["var: signature bar 0.3%"] = x
    x = src.copy(); s = (slice(int(.40 * H), int(.58 * H)), slice(int(.40 * W), int(.58 * W)))
    reg = Image.fromarray(x[s]); rw, rh = reg.size
    x[s] = np.asarray(reg.resize((max(1, rw // 12), max(1, rh // 12)), Image.BOX).resize((rw, rh), Image.NEAREST))
    v["var: mosaic censor 3%"] = x
    im = Image.fromarray(src.copy()); d = ImageDraw.Draw(im)
    try:
        font = ImageFont.load_default(size=max(12, H // 25))
    except TypeError:
        font = ImageFont.load_default()
    d.text((int(.05 * W), int(.05 * H)), "SAMPLE TEXT", fill=(250, 40, 40), font=font)
    v["var: small red text"] = np.asarray(im)
    for pct in (1, 3):
        c, cy = int(pct / 100 * W), int(pct / 100 * H)
        v[f"geo: crop {pct}% + resize back"] = np.asarray(Image.fromarray(src[cy:H - cy, c:W - c]).resize((W, H), Image.LANCZOS))
    return v


def common_size(a, b, maxside=None):
    h, w = min(a.shape[0], b.shape[0]), min(a.shape[1], b.shape[1])
    if maxside:
        s = min(1.0, maxside / max(h, w)); h, w = max(8, int(h * s)), max(8, int(w * s))
    rs = lambda x: x if x.shape[:2] == (h, w) else np.asarray(Image.fromarray(x).resize((w, h), Image.LANCZOS))
    return rs(a), rs(b)


def colour_worst_block(a, b, side=64, grid=16):
    """Proposed 'Local colour difference': worst 4x4-px block RMS on 64x64 area-downsampled BGR thumbnails, % of 255."""
    ta = np.asarray(Image.fromarray(a).resize((side, side), Image.BOX)).astype(np.float64)
    tb = np.asarray(Image.fromarray(b).resize((side, side), Image.BOX)).astype(np.float64)
    d2 = ((ta - tb) ** 2).mean(axis=2); bs = side // grid
    return 100 * np.sqrt(d2.reshape(grid, bs, grid, bs).mean(axis=(1, 3)).max()) / 255


def window_ssim(a, b, side=512, blocks=16):
    ta = np.asarray(Image.fromarray(a).resize((side, side), Image.BOX)).astype(np.float64)
    tb = np.asarray(Image.fromarray(b).resize((side, side), Image.BOX)).astype(np.float64)
    m, S = structural_similarity(ta, tb, channel_axis=2, data_range=255, gaussian_weights=True, sigma=1.5, full=True)
    S = S.mean(axis=2); bs = side // blocks
    return 100 * (1 - m), 100 * (1 - S.reshape(blocks, bs, blocks, bs).mean(axis=(1, 3)).min())


def run(cmd):
    return subprocess.run(cmd, capture_output=True, text=True, timeout=900).stdout


def floats(text):
    out = []
    for tok in text.replace(":", " ").split():
        try:
            out.append(float(tok))
        except ValueError:
            pass
    return out


def find_tools(extra_dirs):
    """shutil.which() only searches PATH, so check the extra folders first (Windows adds .exe itself)."""
    found = {}
    for name in ("ssimulacra2", "butteraugli_main", "butteraugli", "ssimulacra2_rs", "dssim", "bh"):
        hit = None
        for d in extra_dirs:
            hit = shutil.which(name, path=d)
            if hit:
                break
        found[name] = hit or shutil.which(name)
    return found


def write_raw(arr, fn):
    h, w, _ = arr.shape
    with open(fn, "wb") as f:
        f.write(struct.pack("<II", w, h)); f.write(np.ascontiguousarray(arr, dtype=np.uint8).tobytes())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("sources", nargs="+")
    ap.add_argument("--maxside", type=int, default=1024)
    ap.add_argument("--out", default="metric_results.json")
    ap.add_argument("--tool-dir", action="append", default=[], help="extra folder with metric executables (repeatable)")
    args = ap.parse_args()
    extra = args.tool_dir + [d for d in os.environ.get("ANTIDUPL_TOOL_DIRS", "").split(os.pathsep) if d]
    tools = find_tools(extra)
    print("tools:", {k: v for k, v in tools.items() if v} or "none found (only Python metrics will run)")
    tmp = tempfile.mkdtemp()
    fa, fb = os.path.join(tmp, "a.png"), os.path.join(tmp, "b.png")
    rows = []
    for spath in args.sources:
        im = Image.open(spath).convert("RGB"); im.thumbnail((args.maxside, args.maxside), Image.LANCZOS)
        src = np.asarray(im)
        ref_plane = reduced(gray_correct(src))
        for name, var in variants(src).items():
            a, b = common_size(src, var)
            Image.fromarray(a).save(fa); Image.fromarray(b).save(fb)
            r = {"source": os.path.basename(spath), "variant": name}
            r["AntiDupl SSIM"] = antidupl_ssim_difference(ref_plane, reduced(gray_correct(var)))[0]
            r["Colour worst-block 64px"] = colour_worst_block(src, var)
            if imagehash:
                A, B = Image.fromarray(src), Image.fromarray(var)
                for hn, hf in (("aHash", imagehash.average_hash), ("dHash", imagehash.dhash), ("pHash", imagehash.phash), ("wHash", imagehash.whash)):
                    r[hn] = int(hf(A) - hf(B))
            if structural_similarity:
                r["Window colour SSIM mean"], r["Window colour SSIM worst block"] = window_ssim(a, b)
            if compute_ssimulacra2:
                r["SSIMULACRA2 (py, higher=closer)"] = float(compute_ssimulacra2(fa, fb))
            if tools["ssimulacra2"]:          # libjxl reference: prints the score
                v = floats(run([tools["ssimulacra2"], fa, fb]))
                r["SSIMULACRA2 (libjxl, higher=closer)"] = v[0] if v else float("nan")
            if tools["butteraugli_main"]:     # libjxl reference: max-norm, then "3-norm: x"
                v = floats(run([tools["butteraugli_main"], fa, fb]))
                if v:
                    r["Butteraugli max (libjxl)"] = v[0]
                if len(v) > 2:
                    r["Butteraugli 3-norm (libjxl)"] = v[-1]
            if tools["butteraugli"]:
                j = json.loads(run([tools["butteraugli"], "--json", fa, fb]))
                r["Butteraugli max"], r["Butteraugli 3-norm"] = j["score"], j["pnorm_3"]
            if tools["ssimulacra2_rs"]:
                out = run([tools["ssimulacra2_rs"], "image", fa, fb]).split()
                r["SSIMULACRA2 (rs, higher=closer)"] = float(out[-1]) if out else float("nan")
            if tools["dssim"]:
                out = run([tools["dssim"], fa, fb]).split()
                r["DSSIM"] = float(out[0]) if out else float("nan")
            if tools["bh"]:
                a5, b5 = common_size(src, var, 512)
                write_raw(a5, fa + ".raw"); write_raw(b5, fb + ".raw")
                out = run([tools["bh"], fa + ".raw", fb + ".raw"]).split()
                r["Butteraugli C++ @512px"], r["ms/pair @512px"] = float(out[0]), float(out[1])
            rows.append(r)
            print(r["source"], name, {k: round(v, 4) for k, v in r.items() if isinstance(v, (int, float))}, flush=True)
    json.dump(rows, open(args.out, "w"), indent=1)
    keys = [k for k in rows[0] if k not in ("source", "variant", "ms/pair @512px")]
    print("\n| Metric | Duplicates | Variants | Crops | Separates? |\n|---|---|---|---|---|")
    for k in keys:
        grp = lambda p: [r[k] for r in rows if r["variant"].startswith(p) and k in r]
        d, v, g = grp("dup"), grp("var"), grp("geo")
        higher_is_closer = "higher=closer" in k
        sep = (max(v) < min(d)) if higher_is_closer else (min(v) > max(d))
        # ASCII only: a cp932 console cannot encode an en dash.
        print(f"| {k} | {min(d):.4g} - {max(d):.4g} | {min(v):.4g} - {max(v):.4g} | {min(g):.4g} - {max(g):.4g} | {'yes' if sep else 'no'} |")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
