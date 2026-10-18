# 02 — Better comparison engines → new "Algorithm" choices

User's goal: delete copies that only differ by compression/resizing, **keep** "similar but distinct" images (colour variants, expression/text/signature/censor edits). User's decision: add the better metrics as more choices next to *Mean square difference* / *SSIM*, and **switching between them must not redo costly work**. Slower comparisons are acceptable.

## Why the current metric can't do it (even after the bug fixes)

AntiDupl's SSIM is one global window over a 128×128 **grayscale** thumbnail: colour-only changes are invisible and a local edit barely moves global mean/variance/covariance. Experiments (`tools/metric_experiment.py`, 3 of the user's images, 8 duplicate kinds — JPEG q95…q40, WebP q80, 50 %/25 % downscales —, 7 edit kinds — same-luma hue change, local recolour, white box, face-size edit, signature bar, mosaic censor, small red text —, 2 border crops).

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

(The pip `ssimulacra2` Python port disagreed with the reference on downscaled copies — e.g. 51.9 vs 84.7 — so its numbers are not used.)

Conclusions:

* **Hashes / embeddings are the wrong tool here.** They are built to say "same picture" despite edits — great for finding candidates, useless for keeping variants. (Copy-detection embeddings such as SSCD, and CLIP-like ones, deliberately ignore edits; [07](07-settings-study.md) measured SSCD, DINOv2 and SigLIP: no help in telling copies from versions, but candidate finders for crops.)
* **Masking-aware perceptual metrics are the right tool.** Butteraugli's max-norm finds the single worst local difference *after* modelling how much compression noise texture hides — re-saves stay low, local edits (including mosaics) stand out. SSIMULACRA2 is designed to grade compression quality; it is weaker at "is this a different picture".
* **A cheap colour block metric gets most of the way** for colour variants and local edits, at SSIM speed, but cannot see detail-only edits (fine mosaic censoring) and, like everything else, treats crops as edits.

Other tools looked at for ideas: Czkawka/Krokiet (perceptual hashes), dupeGuru picture mode (15×15 block colour averages — the same family as the colour block metric), imagededup (hashes + CNN embeddings), difPy (MSE on tiny thumbnails), AntiDuplX (same algorithm family as AntiDupl). As far as their documented approaches go, none is designed to separate "worse copy" from "variant" — they all aim at fuzzy "same picture" matching, which is what the two-stage design below adds on top.

## Resolution: bigger is not automatically better

Same experiment, varying the comparison size (gap = mildest variant ÷ worst duplicate; >1 means a threshold exists):

| Metric | 32 px | 64 px | 128 px | 256 px | 512 px | 768 px | 1024 px |
|---|---|---|---|---|---|---|---|
| Global SSIM (bilinear or area) | ✗ | ✗ | ✗ | ✗ | ✗ | | |
| Colour block, all variants | 0.17 | 0.32 | 0.36 | 0.43 | | | |
| Colour block, no fine mosaic | **4.2** | **2.9** | 1.45 | 0.85 | | | |
| Butteraugli, all variants | | | | 0.81 | 1.50 | 3.0 | **4.9** |
| Butteraugli, no fine mosaic | | | | 3.7 | 3.5 | 4.9 | 5.2 |
| Butteraugli ms / pair (1 thread) | | | | 65 | 235 | 540 | 990 |

* **Plain pixel metrics get worse with size**: a bigger thumbnail stops averaging away compression noise and starts seeing the detail a downscaled copy lost (duplicates 1.5 → 10.4 from 32 → 256 px) faster than it gains on edits (6.2 → 8.8). Small thumbnails are robust but blind to small or fine edits.
* **Perceptual metrics get better with size** because their masking model discounts the noise — at a cost roughly ×4 per doubling.
* Memory/disk per image ∝ size² (gray 128² = 16 KB, 256² = 64 KB, 512² = 256 KB; colour ×3), and every pixel-wise all-pairs comparison scales the same way. AntiDupl's *Reduced image size* is capped at 128 (`INITIAL_REDUCED_IMAGE_SIZE = 256` with one 2×2 step) — the user already uses the maximum.
* The "fine mosaic" case uses 12-px cells on a 4000-px image (finer than typical censoring); coarser mosaics are easier at every size.

## Design

### Per-image data: compute once, cache, reuse for every mode

Computed in `TDataCollector::FillPixelData` regardless of the selected algorithm and stored in the image DB (`FILE_VERSION` 6 holds the hash, 7 the colour thumbnail and the area-averaged plane; [01 § C](01-difference-correctness.md)):

| Data | Size | Used by |
|---|---|---|
| 128×128 gray plane, **area**-resampled from the full image (T10), + `sum`/`sumSquare` (exact) | 16 KB | Mean square, SSIM |
| 4×4 "fast" data (existing) | 16 B | prefilters |
| 64×64 BGR colour thumbnail, **area**-resampled from the full image | 12 KB | Local colour |
| full-resolution pixel hash (XXH3-64) | 8 B | identity, all modes |

Switching between Mean square / SSIM / Local colour therefore never decodes again — only the comparison loop re-runs. Butteraugli needs bigger images (below) and gets its own caches.

### Mode 3 — "Local colour difference" (fast; T11, on the personal branch)

* Metric: split both 64×64 thumbnails into a 16×16 grid of 4×4-pixel blocks; per block `rms = sqrt(mean over pixels and B,G,R of (a−b)²)`; result `= 100 · max(rms) / 255` (%). `TImageComparer_LocalColor` in `adImageComparer.cpp`.
* Core value `AD_COMPARING_LOCAL_COLOR = 3`: 2 is the .NET side's `AlgorithmComparing.Dinov2`, a search the .NET code runs itself, and the core compares a 2 as SSIM.
* Threshold: whole percent 0–50, default **4** (`THRESHOLD_DIFFERENCE_DEFAULT_LOCAL_COLOR`). On the first test set duplicates ≤ 2.3, edits ≥ 6.6; in the settings study every plain copy is at most 4.1 %, 1.5 % without the 12–25 % copies ([07](07-settings-study.md#antidupls-own-algorithms-size-grey-or-colour-resampling)).
* Cost ≈ SSIM (12 KB per pair), all pairs like `TImageComparer_SSIM`, with an early exit once a block passes the threshold. Prefilter on the existing 4×4 fast data: a cell's grey difference is at most 1.158 times the RMS colour difference of its worst block, so a pair with cells further apart than `ceil(1.158 · threshold) + 3` levels is skipped (3 levels for the rounding in both thumbnails).
* *Ignore frame width* leaves out the border blocks it touches, and turns the prefilter off (the frame's edge need not fall on a block edge).

### Mode 4 — "Perceptual (Butteraugli)" (slow, most accurate; T12, on the personal branch)

* **Implementation:** `google/butteraugli` (`butteraugli.cc/.h`, Apache-2.0, std-lib only) vendored unchanged in `src/AntiDupl/3rd/butteraugli/` with its LICENSE and the commit it came from. libjxl (already a vcpkg dependency) removed its public Butteraugli API in 0.9, so linking it is not an option; vendoring libjxl's faster SIMD version would drag in its internals and Highway. The two give different values (rank correlation 0.87–0.90 on the study's pairs), so the study's libjxl figures don't carry over as thresholds.
* **Candidates:** `TImageComparer_Butteraugli` derives from local colour and runs its check at `BUTTERAUGLI_CANDIDATE_THRESHOLD` (10 %, whatever the user's threshold): in the study every pair up to a libjxl score of 15 at 512 px was within 5.21 %. Pixel-identical pairs get 0 without a score.
* **Input:** each image decoded again from its file (`TImage::Load`, every format the core reads), area-resized (`AreaResize`) to the working size, the longest side 384, 512, 768 or 1024 px (`adCompareOptions.butteraugliSize`, default **768**), smaller images as they are; B, G, R bytes. For a pair, the image with more pixels is area-resized to the other's size and is Butteraugli's reference, so a pair scores the same whichever image the search met first; sRGB to linear light on Butteraugli's 0–255 scale. Turned and mirrored comparisons turn the first working image as `Accept` turns the reduced ones. *Ignore frame width* cuts the frame off both images before Butteraugli runs: its wide filters carry a change in the frame well into the picture, so masking the map afterwards leaves a painted 4 % edge at 34 with a 6 % frame. The score is the map's largest value.
* **No repeated work:** `TButteraugliStore` (`adButteraugli.cpp`), made by `TEngine::Search` for a search with this algorithm and shared by the compare threads: working images in an LRU cache (`BUTTERAUGLI_IMAGE_CACHE_BYTES`; a second thread wanting an image being decoded waits for it), and the scores of pairs in the user folder's `butteraugli.adp`, keyed by both files' CRC-32C and size, the turn, the working size and the frame, with `BUTTERAUGLI_SCORE_VERSION` in the header to bump when a score's computation changes. Not done: TurboJPEG's DCT scaling (decoding straight to near the working size), and a disk cache of working images.
* **Threshold:** Butteraugli's units, no percent; the lists offer halves to 10, whole points to 20, then fives to 50. The default follows the working size (`CoreOptionsForm.THRESHOLD_DIFFERENCE_DEFAULT_BUTTERAUGLI`), and choosing another size in the Options dialog selects its default.

Calibration and cost, the core on the settings study's four illustrations ([07](07-settings-study.md); `tools/core_calibration.py` on `tools/core_search.py` runs, one search per illustration; the AVIF copies left out, which the build couldn't decode before T22, except at 768 px, where with them included every value below is the same). "Plain copies" are the compressed, resized, web and upscaled ones down to a third of the size; the 12–25 % ones are counted apart. Up to 768 px the closest version is one pair of near-identical variants of one illustration, at 1024 px a work-in-progress step (that variant pair: 11.19); the next version is given too. Cost is per scored pair on one of 12 compare threads of the user's PC (24 logical processors), decoding included, on the first search; a second search of the same files reads the scores (13.2 s → 1.1 s for 76 images at 512).

| Working size | Largest plain copy | with 12–25 % copies | Closest version | Next version | Default threshold | ms per pair |
|---|---|---|---|---|---|---|
| 384 | 4.07 | 5.32 | 4.52 | 7.02 | 5 | 111 |
| 512 | 5.00 | 8.27 | 7.20 | 9.03 | 6 | 175 |
| 768 | 7.19 | 7.66 | 9.41 | 9.47 | 8.5 | 411 |
| 1024 | 8.85 | 8.85 | 10.37 | 10.45 | 9.5 | 641 |

At 768 and 1024 px every copy, the tiny ones too, scores below every version; 768 has the wider gap at about two thirds of 1024's cost, hence the default.

### Plumbing

* `enum adAlgorithmComparing` ([AntiDupl.h](../src/AntiDupl/AntiDupl.h)): `AD_COMPARING_LOCAL_COLOR = 3`, `AD_COMPARING_BUTTERAUGLI = 4`, before `AD_COMPARING_SIZE`; the option's range check (`AlgorithmOfComparing` in [adOptions.cpp](../src/AntiDupl/adOptions.cpp)) follows it. `adCompareOptions` ends with `butteraugliSize`, mirrored in `CoreDll.adCompareOptions` and `CoreCompareOptions` (whose initial value is what a profile saved without it loads with).
* `CreateImageComparer` ([adImageComparer.cpp](../src/AntiDupl/adImageComparer.cpp)) returns the new comparers; all of them use the identity rule of [01 § E](01-difference-correctness.md).
* C#: [AlgorithmComparing.cs](../src/AntiDupl.NET.Core/Enums/AlgorithmComparing.cs), the algorithm list in `CoreOptionsForm.InitilizeCompareTabPage` and `MainToolStrip` (`ALGORITHMS`), per-mode threshold lists and defaults (`CoreOptionsForm.ThresholdValues`, `ThresholdMax`, `ThresholdDefault`), strings (English/Russian). The WPF front end lists only mean square and SSIM.
* Optional (makes switching instant without re-searching): store every cheap metric per result (`double ssim, colour, butteraugli`) and show them as extra sortable columns — needs an `adResult` ABI/`.adr` format change.

## Calibrate on real data

Synthetic edits are only a proxy. Before choosing defaults, run `tools/metric_experiment.py` on a handful of the user's real duplicate and variant sets (or add a "copy results with all metrics" clipboard action) and pick thresholds from those numbers. The settings study ([07](07-settings-study.md)) does this on a sample set from the user's archive.

## Known limitations / future work

* Crops and borders: every metric tested scores a 1 % border crop as very different. Fix = align first (search scale/offset on thumbnails, then compare the overlap); design in [07 § Crops](07-settings-study.md#crops) (T19).
* Mirrored/rotated copies: existing *transformed image* option; pixel identity is reset for transforms.
* Which copy is "worse": complementary — see JPEG-quality / bits-per-pixel columns in [06](06-stretch-and-ameliorations.md).
