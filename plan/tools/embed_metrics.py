"""Neural metrics for the settings study (plan 07), for every pair of a
run: embedding distances (100 x (1 - cosine similarity)) and learned
full-reference differences (x 100).

Usage: <python with torch, torchvision, timm and transformers>
           embed_metrics.py <cache> <out> [--siglip FILE] [--sscd FILE]
           [--dinov2 FILE] [--lpips] [--dists] [--torch-home DIR]
           [--pylib DIR ...] [--nr MODELS --set SET]

Reads the pairs from <out>/pairs.csv and the 512 px working copies from
<cache> (both written by settings_study.py), and writes
<out>/pairs-embed.csv with a column per pair metric asked for (and the
columns of the file it replaces that the run doesn't compute), and with
--nr <out>/quality-nr.csv with no-reference quality per image; both are
joined by settings_study.py. Nothing is fetched from the network: every
model comes from a file named here.

--siglip  Google's SigLIP so400m-patch14-384 vision tower (the file ComfyUI
          loads as a CLIP vision model), in the transformers layout;
          squashed to 384 x 384.
--sscd    Meta's SSCD copy-detection model, TorchScript
          (sscd_disc_mixup.torchscript.pt); shorter side 288, as its
          authors evaluate it.
--dinov2  Meta's DINOv2 ViT-S/14 checkpoint (dinov2_vits14_pretrain.pth),
          loaded into timm's model; squashed to 224 x 224, CLS token.
--lpips, --dists
          LPIPS (AlexNet) and DISTS (VGG16) on 256 x 256 copies, aspect
          ignored like the other full-reference metrics. They need the
          `lpips` and `DISTS_pytorch` packages (--pylib: a pip --target
          folder) and torchvision's ImageNet weights in
          <torch-home>/hub/checkpoints (alexnet-owt-7be5be79.pth,
          vgg16-397923af.pth).
--nr      MUSIQ and TOPIQ-NR (KonIQ-10k checkpoints) and NIQE through the
          `pyiqa` package, BRISQUE through OpenCV's quality module; the
          folder holds musiq_koniq_ckpt-e95806b9.pth,
          cfanet_nr_koniq_res50-9a73138b.pth, niqe_modelparameters.mat,
          brisque_model_live.yml and brisque_range_live.yml.
"""
import argparse
import csv
import os
import sys

import numpy as np
from PIL import Image

IMAGENET_MEAN = np.array([0.485, 0.456, 0.406], dtype=np.float32)
IMAGENET_STD = np.array([0.229, 0.224, 0.225], dtype=np.float32)


def as_tensor(im, mean=None, std=None):
    import torch
    x = np.asarray(im.convert("RGB"), dtype=np.float32) / 255
    if mean is not None:
        x = (x - mean) / std
    return torch.from_numpy(np.ascontiguousarray(x)).permute(2, 0, 1)[None]


def siglip(path, device):
    import torch
    from safetensors.torch import load_file
    from transformers import SiglipVisionConfig, SiglipVisionModel
    config = SiglipVisionConfig(hidden_size=1152, intermediate_size=4304, num_hidden_layers=27,
                                num_attention_heads=16, image_size=384, patch_size=14,
                                hidden_act="gelu_pytorch_tanh", layer_norm_eps=1e-6)
    model = SiglipVisionModel(config)
    state = load_file(path)
    if not any(k.startswith("vision_model.") for k in model.state_dict()):
        # transformers 5 names the tower's tensors without the prefix.
        state = {k.removeprefix("vision_model."): v for k, v in state.items()}
    # strict: every tensor of the file has its place and none is missing.
    model.load_state_dict(state, strict=True)
    model = model.to(device).float().eval()

    def embed(im):
        x = as_tensor(im.convert("RGB").resize((384, 384), Image.BICUBIC), np.float32(0.5), np.float32(0.5))
        with torch.no_grad():
            return model(pixel_values=x.to(device)).pooler_output[0]
    return embed


def sscd(path, device):
    import torch
    model = torch.jit.load(path, map_location=device).eval()

    def embed(im):
        w, h = im.size
        f = 288 / min(w, h)
        x = as_tensor(im.convert("RGB").resize((max(1, round(w * f)), max(1, round(h * f))), Image.BILINEAR),
                      IMAGENET_MEAN, IMAGENET_STD)
        with torch.no_grad():
            return model(x.to(device))[0]
    return embed


def dinov2(path, device):
    import timm
    import torch
    from timm.models.vision_transformer import checkpoint_filter_fn
    model = timm.create_model("vit_small_patch14_dinov2", pretrained=False, num_classes=0, dynamic_img_size=True)
    state = checkpoint_filter_fn(torch.load(path, map_location="cpu", weights_only=True), model)
    model.load_state_dict(state, strict=True)
    model = model.to(device).eval()

    def embed(im):
        x = as_tensor(im.convert("RGB").resize((224, 224), Image.BICUBIC), IMAGENET_MEAN, IMAGENET_STD)
        with torch.no_grad():
            return model(x.to(device))[0]
    return embed


NR_LOWER_BETTER = {"niqe", "brisque"}


def open_full(path):
    """The file's pixels at full size (JPEG XL through libjxl's djxl)."""
    if not path.lower().endswith(".jxl"):
        return Image.open(path).convert("RGB")
    import subprocess
    import tempfile
    djxl = os.path.join(os.environ.get("LIBJXL", ""), "djxl.exe")
    with tempfile.TemporaryDirectory() as tmp:
        out = os.path.join(tmp, "decoded.png")
        subprocess.run([djxl, path, out, "--quiet"], check=True, capture_output=True)
        return Image.open(out).convert("RGB")


def no_reference(set_dir, files, device, models):
    """Per image, no-reference quality on a central 1024 px crop at full
    resolution, where compression shows: MUSIQ and TOPIQ (both trained on
    KonIQ-10k ratings; higher is better), NIQE and BRISQUE (lower is
    better). Returns {(case, file): {name: score}}."""
    import types

    import cv2
    import torch
    # TOPIQ's module imports a face-alignment helper used only for face
    # crops (align_crop_face), which these images never take.
    for name in ("facexlib", "facexlib.utils", "facexlib.utils.face_restoration_helper"):
        sys.modules.setdefault(name, types.ModuleType(name))
    sys.modules["facexlib.utils.face_restoration_helper"].FaceRestoreHelper = object
    from pyiqa.archs.musiq_arch import MUSIQ
    from pyiqa.archs.niqe_arch import NIQE
    from pyiqa.archs.topiq_arch import CFANet
    nets = {
        "musiq": MUSIQ(pretrained_model_path=os.path.join(models, "musiq_koniq_ckpt-e95806b9.pth")),
        "topiq-nr": CFANet(semantic_model_name="resnet50", model_name="cfanet_nr_koniq_res50", use_ref=False,
                           backbone_pretrain=False,
                           pretrained_model_path=os.path.join(models, "cfanet_nr_koniq_res50-9a73138b.pth")),
        "niqe": NIQE(pretrained_model_path=os.path.join(models, "niqe_modelparameters.mat")),
    }
    nets = {n: m.to(device).eval() for n, m in nets.items()}
    brisque = (os.path.join(models, "brisque_model_live.yml"), os.path.join(models, "brisque_range_live.yml"))
    out = {}
    for case, file in files:
        im = open_full(os.path.join(set_dir, case, file))
        w, h = im.size
        side = min(1024, w, h)
        x0, y0 = (w - side) // 2, (h - side) // 2
        part = im.crop((x0, y0, x0 + side, y0 + side))
        x = as_tensor(part).to(device)
        with torch.no_grad():
            scores = {n: float(m(x).flatten()[0]) for n, m in nets.items()}
        bgr = np.ascontiguousarray(np.asarray(part)[..., ::-1])
        scores["brisque"] = float(cv2.quality.QualityBRISQUE_compute(bgr, *brisque)[0])
        out[(case, file)] = scores
    return out


def full_reference(names, device):
    """name -> function(a, b) on batches of 256 x 256 tensors in [0, 1]."""
    import torch
    out = {}
    if "lpips-alex" in names:
        import lpips
        net = lpips.LPIPS(net="alex", verbose=False).to(device).eval()
        out["lpips-alex"] = lambda a, b: net(a * 2 - 1, b * 2 - 1).flatten()
    if "dists" in names:
        import DISTS_pytorch
        from DISTS_pytorch import DISTS
        # DISTS() would read its weights from the Python installation's
        # root (sys.prefix); the package folder holds a copy.
        dists = DISTS(load_weights=False)
        weights = torch.load(os.path.join(os.path.dirname(DISTS_pytorch.__file__), "weights.pt"), map_location="cpu",
                             weights_only=True)
        dists.alpha.data, dists.beta.data = weights["alpha"], weights["beta"]
        dists = dists.to(device).eval()
        out["dists"] = lambda a, b: dists(a, b, require_grad=False, batch_average=False).flatten()
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cache")
    ap.add_argument("out")
    ap.add_argument("--siglip")
    ap.add_argument("--sscd")
    ap.add_argument("--dinov2")
    ap.add_argument("--lpips", action="store_true")
    ap.add_argument("--dists", action="store_true")
    ap.add_argument("--torch-home", help="folder holding hub/checkpoints with torchvision's weights")
    ap.add_argument("--pylib", action="append", default=[],
                    help="a package folder (lpips, DISTS_pytorch, pyiqa, OpenCV); repeatable")
    ap.add_argument("--nr", metavar="MODELS",
                    help="no-reference quality per image, models from this folder (quality-nr.csv); needs --set")
    ap.add_argument("--set", help="the sample set (for --nr: the files at full size)")
    a = ap.parse_args()
    if a.torch_home:
        os.environ["TORCH_HOME"] = a.torch_home
    for p in reversed(a.pylib):
        sys.path.insert(0, p)
    import torch
    device = "cuda" if torch.cuda.is_available() else "cpu"
    with open(os.path.join(a.out, "pairs.csv"), encoding="utf-8") as f:
        pairs = [(r["case_a"], r["a"], r["case_b"], r["b"]) for r in csv.DictReader(f)]
    files = sorted({(p[0], p[1]) for p in pairs} | {(p[2], p[3]) for p in pairs})

    def working(case, file):
        return Image.open(os.path.join(a.cache, case, file.rsplit(".", 1)[0] + "-512.png"))

    columns = {}
    embedders = [(n, f(p, device)) for n, f, p in (("siglip-so400m", siglip, a.siglip), ("sscd", sscd, a.sscd),
                                                    ("dinov2-vits14", dinov2, a.dinov2)) if p]
    for name, embed in embedders:
        vectors = {}
        for key in files:
            v = embed(working(*key)).float()
            vectors[key] = torch.nn.functional.normalize(v, dim=0).cpu().numpy()
        columns[name] = [100 * (1 - float(np.dot(vectors[(ca, fa)], vectors[(cb, fb)]))) for ca, fa, cb, fb in pairs]
        print(f"{name}: {len(vectors)} images on {device}", flush=True)
    wanted = [n for n, on in (("lpips-alex", a.lpips), ("dists", a.dists)) if on]
    if wanted:
        tensors = {key: as_tensor(working(*key).convert("RGB").resize((256, 256), Image.BOX)) for key in files}
        for name, fn in full_reference(wanted, device).items():
            values = []
            for k in range(0, len(pairs), 64):
                batch = pairs[k:k + 64]
                x = torch.cat([tensors[(ca, fa)] for ca, fa, _, _ in batch]).to(device)
                y = torch.cat([tensors[(cb, fb)] for _, _, cb, fb in batch]).to(device)
                with torch.no_grad():
                    values.extend((100 * fn(x, y)).cpu().tolist())
            columns[name] = values
            print(f"{name}: {len(values)} pairs on {device}", flush=True)
    if columns:
        path = os.path.join(a.out, "pairs-embed.csv")
        # The columns of the file this one replaces that this run doesn't
        # compute are kept, for the pairs they have: a model file can be
        # gone by the next run (SigLIP's is), and its values with it.
        kept = {}
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                reader = csv.DictReader(f)
                old = [n for n in (reader.fieldnames or [])[4:] if n not in columns]
                rows = {(r["case_a"], r["a"], r["case_b"], r["b"]): r for r in reader} if old else {}
            for n in old:
                kept[n] = [rows[p][n] if p in rows else "" for p in pairs]
            if kept:
                print(f"kept from the earlier {path}: {', '.join(kept)}", flush=True)
        columns = {**kept, **columns}
        with open(path, "w", encoding="utf-8", newline="") as f:
            w = csv.writer(f)
            w.writerow(["case_a", "a", "case_b", "b", *columns])
            for k, (ca, fa, cb, fb) in enumerate(pairs):
                w.writerow([ca, fa, cb, fb, *(columns[n][k] for n in columns)])
        print(f"{len(pairs)} pairs written", flush=True)
    if a.nr:
        scores = no_reference(a.set, files, device, a.nr)
        names = list(next(iter(scores.values())))
        with open(os.path.join(a.out, "quality-nr.csv"), "w", encoding="utf-8", newline="") as f:
            w = csv.writer(f)
            w.writerow(["case", "file", *names])
            for (case, file), s in scores.items():
                w.writerow([case, file, *(s[n] for n in names)])
        print(f"{len(scores)} images scored ({', '.join(names)})", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
