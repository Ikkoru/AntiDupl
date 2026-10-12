# 07 — Settings study: reduced size, grey or colour, per algorithm

Which *Reduced image size*, grey or colour, and which resampling make each comparison algorithm find copies (to delete) without pairing up versions (to keep)? Measured on a set built from the user's own images; the raw numbers are on the user's PC (workspace `Research\results\`), rebuilt by the tools below.

## The set

Two digital illustrations from the user's archive (4000 × 6036 and 2500 × 3750 px), each with the artist's own versions and work-in-progress steps, and copies and edits made from the final image:

| Kind | Per illustration |
|---|---|
| original | the artist's final PNG |
| variant | the artist's other versions (13 and 9): local changes covering under 0.1 % to 8.6 % of the picture |
| step | 8 work-in-progress pictures, line sketch → flat colours → shading → near-final |
| copy | JPEG q95 4:4:4, q80 and q50 4:2:0, WebP q80, 75 % PNG, 50 % JPEG q85, 25 % PNG |
| gray | greyscale |
| crop | 1 % and 5 % cut from each side |
| edit | small text, black bar, mosaic, local recolour (on the most detailed region), global recolour |

Every pair within an illustration is compared (37 and 33 images → 1,194 pairs), and every pair across the two (1,221 unrelated pairs). Classes ("clean" = the original or a copy):

| Class | Pairs |
|---|---|
| copy: original~copy, copy~copy | 56 |
| sketch, wip-far, wip-close: clean~step, by the step's position (first quarter, middle, last quarter) | 32, 64, 32 |
| variant-minor, -medium, -major: clean~variant and variant~variant, under 1 %, 1–5 %, 5 % or more of the picture changed | 84, 95, 111 |
| edit-minor (text, bar), edit-medium (mosaic, local recolour), edit-major (global recolour) | 32, 32, 16 |
| gray, crop: reported only; whether they are copies is the user's call | 16, 32 |

## Settings and method

Per algorithm: size 16 / 32 / 64 / 128; grey (AntiDupl's plane) or colour (the same per B, G, R plane: SSIM averaged over the planes, mean square over all values); resampling *bilinear* (AntiDupl's: bilinear to 256, then 2×2 reductions) or *area* (box filter straight to the size, [01 § G](01-difference-correctness.md)). Algorithms: AntiDupl's SSIM and mean square difference, and the planned local colour metric ([02](02-comparison-modes.md), mode 3: worst 4×4-block colour RMS, area-resampled). The Python pipeline reproduces the core: SSIM at sizes 128 and 32 on 256 pairs each, largest deviation 5e-7.

The question asked of each setting: with the threshold set just high enough to find every copy, how many versions does it pair up as well?

## Results

Versions paired up (of 498) with the threshold at the highest copy:

| Setting | All copies | Without the 25 % copy |
|---|---|---|
| local colour, area, 64 | **1** (threshold 1.57) | **1** (0.85) |
| local colour, area, 32 / 128 | 2 / 10 | 1 / 1 |
| SSIM, grey, area, 64 | 16 (0.014) | 10 (0.006) |
| SSIM, colour, area, 64 | 18 (0.019) | 12 (0.011) |
| SSIM, grey, area, 128 | 41 (0.043) | 10 (0.011) |
| SSIM, grey, bilinear, 32 | 50 (0.019) | 16 (0.008) |
| SSIM, grey, bilinear, 128 (the user's setting) | 96 (0.23) | 38 (0.060) |
| mean square, grey, area, 64 | 18 (0.43) | 11 (0.28) |
| mean square, grey, bilinear, 128 | 95 (1.67) | 35 (0.87) |

* **Sketches, work-in-progress steps, major variants and major edits are kept apart by every setting.** The hard cases are versions that change under 1 % of the picture, and small edits. The one pair the local colour metric misses changes 0.01 % of the picture: nothing at thumbnail scale sees it, but pixel identity (T8) still keeps it from showing 0.00.
* **Local colour at 64 px** finds every copy, including the 25 % one, and pairs up one version. It should be T11's default size.
* **Area resampling beats AntiDupl's bilinear pipeline at every size** for SSIM and mean square (T10). With area, 64 is the best size; with today's bilinear pipeline, 32 beats 128 (50 against 96).
* **Grey or colour makes no difference** for variants and edits. It decides only the greyscale version: grey settings see it as a copy (16 of 16), colour settings as a version (0 of 16).
* **AntiDupl's thresholds are too coarse.** The thresholds that find every copy are 0.004–0.23 % for SSIM and 0.19–1.7 % for mean square, while the smallest non-zero threshold is 1 %. At the user's setting (SSIM, grey, 128) a 1 % threshold pairs up 231 of the 498 versions, among them 36 major variants. Thresholds need finer steps (task T16).
* **The 25 % copy sets the threshold** of most settings: a copy shrunk to a quarter is the farthest from the original. Without it, thresholds drop to between a quarter and a half, and the existing algorithms pair up 10–43 versions instead of 16–96.

## Limits and next steps

* Two illustrations by one artist, digital painting; other styles (photos, pixel art, line art) and other artists' variant habits may shift the sizes. More sets: the user's other candidates.
* Butteraugli (T12) is not in the study yet: it needs larger images and minutes per run, so it comes once the cheap settings are settled.
* Crops count in neither group: every setting here scores them far from the original (alignment would be needed, [02](02-comparison-modes.md)).

## Tools

* `tools/study_set.py <config> <out>`: copies the files named in a config (outside this repository: it names files in the user's archive) and derives the copies and edits; `CACHEDIR.TAG` on the output.
* `tools/settings_study.py <set> <out>`: `pairs.csv` (every pair, every setting) and `summary.md` (the tables above, and each class's range per setting).
