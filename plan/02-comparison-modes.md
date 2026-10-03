# 02 — Better comparison engines → new "Algorithm" choices

User's goal: delete copies that only differ by compression/resizing, **keep** "similar but distinct" images
(colour variants, expression/text/signature/censor edits). User's decision: add the better metrics as more
choices next to *Mean square difference* / *SSIM*, and **switching between them must not redo costly work**.
Slower comparisons are acceptable.

## Why the current metric can't do it (even after the bug fixes)

AntiDupl's SSIM is one global window over a 128×128 **grayscale** thumbnail: colour-only changes are invisible
and a local edit barely moves global mean/variance/covariance. Experiments (`tools/metric_experiment.py`,
3 of the user's images, 8 duplicate kinds — JPEG q95…q40, WebP q80, 50 %/25 % downscales —, 7 edit kinds —
same-luma hue change, local recolour, white box, face-size edit, signature bar, mosaic censor, small red
text —, 2 border crops).

Full-resolution sources:

| Metric | Duplicates | Variants (edits) | Crops 1–3 % | Separates? |
|---|---|---|---|---|
| AntiDupl SSIM @128 (correct decode) | 0.0005 – 0.68 | **0.0026** – 2.24 | 6.4 – 41 | no — same-luma colour variant 0.0026 |
| Colour worst-block, 64 px (proposed cheap metric) | 0.17 – 2.3 | 0.74 (fine mosaic) / **6.65** others – 47 | 19 – 43 | yes, except fine mosaic |
| **Butteraugli max-norm @512 px** (google/butteraugli C++) | 0.35 – 3.8 | 5.7 (fine mosaic) / 13 others – 147 | 68 – 112 | **yes** |

Sources downscaled to 1024 px first (faster run, same variants):

| Metric | Duplicates | Variants (edits) | Crops 1–3 % | Separates? |
|---|---|---|---|---|
| Perceptual hashes a/d/p/wHash (bits of 64) | 0 – 2 | **0** – 6 | 0 – 9 | no — most edits score 0 |
| DSSIM | 0.0002 – 0.0048 | 0.0003 – 0.092 | 0.19 – 0.88 | no |
| Windowed colour SSIM, mean / worst block (%) | 0.40 – 7.0 / 1.2 – 22 | 0.05 – 24 / 4.2 – 94 | 31 – 77 / 100 – 114 | no |
| SSIMULACRA2 (Rust port validated against libjxl; higher = closer) | 58 – 90 | −40 – 54 | −652 – −64 | barely (4 points) |
| Butteraugli max-norm (Rust port, 1024 px) | 1.4 – 7.0 | 21 – 186 | 106 – 179 | **yes (3×)** |

(The pip `ssimulacra2` Python port disagreed with the reference on downscaled copies — e.g. 51.9 vs 84.7 —
so its numbers are not used.)

Conclusions:

* **Hashes / embeddings are the wrong tool here.** They are built to say "same picture" despite edits —
  great for finding candidates, useless for keeping variants. (Copy-detection embeddings such as SSCD/CLIP
  deliberately ignore edits; not pursued.)
* **Masking-aware perceptual metrics are the right tool.** Butteraugli's max-norm finds the single worst
  local difference *after* modelling how much compression noise texture hides — re-saves stay low, local
  edits (including mosaics) stand out. SSIMULACRA2 is designed to grade compression quality; it is weaker at
  "is this a different picture".
* **A cheap colour block metric gets most of the way** for colour variants and local edits, at SSIM speed,
  but cannot see detail-only edits (fine mosaic censoring) and, like everything else, treats crops as edits.

Other tools looked at for ideas: Czkawka/Krokiet (perceptual hashes), dupeGuru picture mode (15×15 block
colour averages — the same family as the colour block metric), imagededup (hashes + CNN embeddings), difPy
(MSE on tiny thumbnails), AntiDuplX (same algorithm family as AntiDupl). As far as their documented
approaches go, none is designed to separate "worse copy" from "variant" — they all aim at fuzzy "same
picture" matching, which is what the two-stage design below adds on top.

## Resolution: bigger is not automatically better

Same experiment, varying the comparison size (gap = mildest variant ÷ worst duplicate; >1 means a threshold
exists):

| Metric | 32 px | 64 px | 128 px | 256 px | 512 px | 768 px | 1024 px |
|---|---|---|---|---|---|---|---|
| Global SSIM (bilinear or area) | ✗ | ✗ | ✗ | ✗ | ✗ | | |
| Colour block, all variants | 0.17 | 0.32 | 0.36 | 0.43 | | | |
| Colour block, no fine mosaic | **4.2** | **2.9** | 1.45 | 0.85 | | | |
| Butteraugli, all variants | | | | 0.81 | 1.50 | 3.0 | **4.9** |
| Butteraugli, no fine mosaic | | | | 3.7 | 3.5 | 4.9 | 5.2 |
| Butteraugli ms / pair (1 thread) | | | | 65 | 235 | 540 | 990 |

* **Plain pixel metrics get worse with size**: a bigger thumbnail stops averaging away compression noise and
  starts seeing the detail a downscaled copy lost (duplicates 1.5 → 10.4 from 32 → 256 px) faster than it
  gains on edits (6.2 → 8.8). Small thumbnails are robust but blind to small or fine edits.
* **Perceptual metrics get better with size** because their masking model discounts the noise — at a cost
  roughly ×4 per doubling.
* Memory/disk per image ∝ size² (gray 128² = 16 KB, 256² = 64 KB, 512² = 256 KB; colour ×3), and every
  pixel-wise all-pairs comparison scales the same way. AntiDupl's *Reduced image size* is capped at 128
  (`INITIAL_REDUCED_IMAGE_SIZE = 256` with one 2×2 step) — the user already uses the maximum.
* The "fine mosaic" case uses 12-px cells on a 4000-px image (finer than typical censoring); coarser mosaics
  are easier at every size.

## Design

### Per-image data: compute once, cache, reuse for every mode

Computed in `TDataCollector::FillPixelData` regardless of the selected algorithm and stored in the image
DB (same FILE_VERSION 5 bump as [01](01-difference-correctness.md)):

| Data | Size | Used by |
|---|---|---|
| 128×128 gray plane + `sum`/`sumSquare` (exact) | 16 KB | Mean square, SSIM |
| 4×4 "fast" data (existing) | 16 B | prefilters |
| 64×64 BGR colour thumbnail, **area**-resampled from the full image | 12 KB | Local colour |
| full-resolution pixel hash (XXH3-64) | 8 B | identity, all modes |

Switching between Mean square / SSIM / Local colour therefore never decodes again — only the comparison
loop re-runs. Butteraugli needs bigger images (below) and gets its own caches.

### Mode 3 — "Local colour difference" (fast)

* Metric: split both 64×64 thumbnails into a 16×16 grid of 4×4-pixel blocks; per block
  `rms = sqrt(mean over pixels and B,G,R of (a−b)²)`; result `= 100 · max(rms) / 255` (%).
* Threshold: integer % like today; on the test set duplicates ≤ 2.3, edits ≥ 6.6 → default **4**.
* Cost ≈ SSIM (12 KB per pair). All-pairs like `TImageComparer_SSIM`, or prune with the existing 4×4 fast
  data: worst-block colour RMS ≥ |mean luma difference| / 1.16 for any region, so a fast-data luma difference
  above `1.16 · threshold · 2.55` (plus a safety margin for the different resampling) can be skipped safely.
* Respect *Ignore frame width* by masking border blocks.

### Mode 4 — "Perceptual (Butteraugli)" (slow, most accurate)

* **Candidates:** run Local colour (or SSIM) internally with a generous threshold (e.g. colour ≤ 15) → only
  plausible pairs reach Butteraugli.
* **Input:** both images at a common working size (aspect from the smaller image, longest side **512** by
  default; option 384/512/768/1024 — the user may prefer 768 for fine-detail edits). Decode on demand with
  TurboJPEG DCT scaling (`tjGetScalingFactors`, decode at 1/2–1/8 straight to near the target) + area
  resample; convert sRGB→linear.
* **Implementation:** vendor `google/butteraugli` (`butteraugli.cc/.h`, Apache-2.0, std-lib only) into
  `src/AntiDupl/3rd/butteraugli/` with its LICENSE. libjxl (already a vcpkg dependency, 0.11.1) removed its
  public Butteraugli API in 0.9, so linking it is not an option; vendoring libjxl's faster SIMD version is
  possible but drags in its internals/Highway.
* **No repeated work:** per-pair score cache keyed by `(crc32c, size)` of both files + working size + metric
  version, persisted in the user folder (e.g. `pairs\butteraugli.adp`); optionally a lazily-filled per-image
  working-size thumbnail cache (lossless) so an image in several candidate pairs is decoded once.
* Parallelise over compare threads; report progress.
* Threshold: Butteraugli units (duplicates ≤ ~4, edits ≥ ~6–20 depending on size) → default **5** at 512 px.

### Plumbing

* `enum adAlgorithmComparing` ([AntiDupl.h:385](../src/AntiDupl/AntiDupl.h#L385)): add
  `AD_COMPARING_LOCAL_COLOR = 2`, `AD_COMPARING_BUTTERAUGLI = 3` before `AD_COMPARING_SIZE` — no struct layout
  change; range check in [adOptions.cpp:109](../src/AntiDupl/adOptions.cpp#L109) follows automatically.
* `CreateImageComparer` ([adImageComparer.cpp:421](../src/AntiDupl/adImageComparer.cpp#L421)) returns the new
  comparers; all of them use the identity rule of [01 § E](01-difference-correctness.md).
* C#: [AlgorithmComparing.cs](../src/AntiDupl.NET.Core/Enums/AlgorithmComparing.cs), the combo boxes in
  [CoreOptionsForm.cs:233-245](../src/AntiDupl.NET.WinForms/Form/CoreOptionsForm.cs#L233) and `MainToolStrip`,
  per-mode threshold ranges/defaults (`THRESHOLD_DIFFERENCE_*`), strings (English/Russian).
* Optional (makes switching instant without re-searching): store every cheap metric per result
  (`double ssim, colour, butteraugli`) and show them as extra sortable columns — needs an `adResult`
  ABI/`.adr` format change.

## Calibrate on real data

Synthetic edits are only a proxy. Before choosing defaults, run `tools/metric_experiment.py` on a handful of
the user's real duplicate and variant sets (or add a "copy results with all metrics" clipboard action) and
pick thresholds from those numbers.

## Known limitations / future work

* Crops and borders: every metric tested scores a 1 % border crop as very different. Fix = align first
  (search scale/offset on thumbnails, then compare the overlap).
* Mirrored/rotated copies: existing *transformed image* option; pixel identity is reset for transforms.
* Which copy is "worse": complementary — see JPEG-quality / bits-per-pixel columns in [06](06-stretch-and-ameliorations.md).
