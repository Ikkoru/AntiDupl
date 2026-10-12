"""Neural image embeddings for the settings study (plan 07): the cosine
distance between two images' embeddings, for every pair of a run.

Usage: <python with torch and transformers> embed_metrics.py <cache> <out>
           --siglip <sigclip_vision_patch14_384.safetensors>

Reads the pairs from <out>/pairs.csv and the 512 px working copies from
<cache> (both written by settings_study.py), and writes
<out>/pairs-embed.csv, which settings_study.py joins to the other metrics.
The value is 100 x (1 - cosine similarity).

--siglip: Google's SigLIP so400m-patch14-384 vision tower (the file
ComfyUI loads as a CLIP vision model), in the transformers layout; its
architecture is set here, so nothing is fetched from the network.
"""
import argparse
import csv
import os
import sys

import numpy as np
import torch
from PIL import Image


def siglip(path, device):
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
        x = np.asarray(im.convert("RGB").resize((384, 384), Image.BICUBIC), dtype=np.float32) / 255
        x = torch.from_numpy((x - 0.5) / 0.5).permute(2, 0, 1)[None].to(device)
        with torch.no_grad():
            v = model(pixel_values=x).pooler_output[0]
        return torch.nn.functional.normalize(v, dim=0).cpu().numpy()

    return embed


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cache")
    ap.add_argument("out")
    ap.add_argument("--siglip", required=True)
    a = ap.parse_args()
    device = "cuda" if torch.cuda.is_available() else "cpu"
    embed = siglip(a.siglip, device)
    with open(os.path.join(a.out, "pairs.csv"), encoding="utf-8") as f:
        pairs = [(r["case_a"], r["a"], r["case_b"], r["b"]) for r in csv.DictReader(f)]
    vectors = {}
    for case, file in sorted({(p[0], p[1]) for p in pairs} | {(p[2], p[3]) for p in pairs}):
        work = os.path.join(a.cache, case, file.rsplit(".", 1)[0] + "-512.png")
        vectors[(case, file)] = embed(Image.open(work))
    print(f"{len(vectors)} images embedded on {device}", flush=True)
    with open(os.path.join(a.out, "pairs-embed.csv"), "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["case_a", "a", "case_b", "b", "siglip-so400m"])
        for ca, fa, cb, fb in pairs:
            cos = float(np.dot(vectors[(ca, fa)], vectors[(cb, fb)]))
            w.writerow([ca, fa, cb, fb, 100 * (1 - cos)])
    print(f"{len(pairs)} pairs written", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
