# Reproduction & experiment tools

Python 3.10+. `pip install -r requirements.txt`. Nothing here is part of the build; it exists so every number quoted in [`../`](../README.md) can be re-checked on your machine (the scripts run on Windows too).

| Script | What it shows | Example |
|---|---|---|
| `adsim.py` | Library: bit-faithful copy of AntiDupl's reduced-image pipeline (gray conversion, Simd bilinear resize, 2×2 reduce) and of the current float32 SSIM arithmetic, plus the proposed fixed versions. | — |
| `repro_difference.py` | For image pairs: which decoder the current build uses per file, the Difference the current build shows, and the value after the fixes. | `python repro_difference.py "Identical but 0.22 (1).jpg" "Identical but 0.22 (2).jpg"` → current `0.217453` (shows **0.22**), after fixes `0` |
| `float_noise.py` | ~30 % of *identical* 128×128 planes get Difference 7.6e-6 / 1.5e-5 with the current arithmetic → shown as 0.00 but not green, and dropped at threshold 0 %. | `python float_noise.py a.jpg b.jpg` |
| `metric_experiment.py` | Synthesises duplicates (re-saves, resizes) and variants (colour/local edits, mosaic, text, crops) from your images and compares candidate metrics. Uses the optional external tools below when they are on `PATH` or in a `--tool-dir` / `ANTIDUPL_TOOL_DIRS` folder. | `python metric_experiment.py img1.jpg img2.png --maxside 1024 --tool-dir <libjxl bin folder>` |
| `butteraugli_harness/` | 50-line C++ harness around the standalone `google/butteraugli` (Apache-2.0) used for the timing row in [02](../02-comparison-modes.md). Build line in the file header. Put the binary on `PATH` or in a `--tool-dir` folder as `bh`. | — |
| `antidupl.ExifTool_config` | ExifTool config that makes the PNG keywords used by ComfyUI / InvokeAI / Fooocus writable. Destination in the product: `data/` next to the exe (see [05-metadata-merge.md](../05-metadata-merge.md)). | `exiftool -config antidupl.ExifTool_config …` |

Optional external tools for `metric_experiment.py`: the libjxl reference builds `ssimulacra2` and `butteraugli_main` (see [`../README.md`](../README.md#tools)), and these Rust ports, which need the Rust toolchain and add nothing the libjxl tools don't measure except DSSIM:

```
cargo install butteraugli-cli                         # 'butteraugli'  (pure-Rust port of libjxl butteraugli)
cargo install ssimulacra2_rs --no-default-features    # 'ssimulacra2_rs' (default features need VapourSynth)
cargo install dssim                                   # 'dssim'
```

The user's `Examples.zip` images are not committed (size/copyright); pass their paths on the command line.
