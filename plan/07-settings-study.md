# 07 — Settings study: which algorithm and setting for which kind of difference

Which comparison algorithm, reduced size, grey or colour, and resampling find the copies of a picture (to delete) without pairing up its versions (to keep), for each kind of difference: compression, lower resolution, upscaling, crops and so on; and which property of the files tells the worse copy. Measured on a sample set built from the user's archive. The raw numbers are on the user's PC (workspace `Research\results\`: `summary.md` holds every table, also those not repeated here), rebuilt by the tools at the end.

## The set

Four digital illustrations by one artist (2470–4000 px wide, PNG), each with:

| Kind | Per illustration |
|---|---|
| original | the artist's final image |
| variant | the artist's other versions (13, 9, 2 and 0): local changes from under 0.1 % of the picture to most of it |
| step | 8–10 work-in-progress pictures, sketch to near-final; one illustration's steps are on a slightly larger canvas than its final |
| copy: compression | JPEG q100 and q95 (4:4:4), q90 down to q30 (4:2:0), q85 re-encoded three times; WebP q90/75/50; AVIF q60; JPEG XL distance 1 and 4 |
| copy: resolution | 90, 75, 50, 33, 25 and 12 % (Lanczos, PNG); 50 % bilinear and nearest neighbour |
| copy: web | 50 % as JPEG q85, 25 % as JPEG q75 |
| copy: upscaled | shrunk to 50 % and 25 %, then blown back up to full size |
| copy: processed | sharpened, blurred (1 px), brightness +5 %, saturation +15 % |
| crop | 1, 2, 5, 10, 20 % cut from each side; 10 % from one side; the centre square; 5 % cut, then resized back to full size |
| overlay | a white border; a small watermark in a corner; large semi-transparent text across the middle |
| greyscale, transform | greyscale; mirrored; rotated 90° |
| edit | small text; a black bar; mosaic; a smudged region; a cloned patch; a local recolour (all on the most detailed regions); a global recolour |

Every pair within an illustration is compared, and each final image against every image of the other three: 9,830 pairs.

| Class | Pairs |
|---|---|
| copy: the original and its copies, any two | 1,984, of which 1,512 **plain** (no processed copy in the pair) |
| variant-minor, -medium, -major: the original or a copy against a variant, or two variants; under 1 %, 1–5 %, 5 % or more of the picture changed | 226, 194, 463 |
| sketch, wip-far, wip-close: the original or a copy against a step in the first quarter, middle, last quarter of the steps | 256, 544, 288 |
| edit-minor (text, bar), edit-medium (mosaic, smudge, clone, local recolour), edit-major (global recolour) | 256, 512, 128 |
| crop, overlay, greyscale, transform: the user's call whether these are copies | 1,024, 384, 128, 256 |
| unrelated: a final against another illustration's image | 804 |
| other (step~step, variant~edit, …): not judged | 2,383 |

The versions (variant, step and edit classes) add up to 2,867 pairs.

## Method

Every algorithm gives each pair a value; sorted by it, smallest first, the results come in the order the user works through them. The measure is **versions before the last copy**: how many version pairs come before the last copy pair, so how many versions the user has to look at (and mark as mistakes) before having seen every copy. A threshold set just high enough to find every copy pairs up exactly those versions. **AUC** in `summary.md`: the chance that a copy pair comes before a version pair.

Algorithms, all as a difference (0 = identical):

* AntiDupl's SSIM and mean square difference at every setting: size 16–128; grey (AntiDupl's plane) or colour (the same per B, G, R plane); *bilinear* (AntiDupl's resampling: bilinear to 256, then 2×2 reductions) or *area* (box filter straight to the size, [01 § G](01-difference-correctness.md)). The Python pipeline (`tools/adsim.py`) reproduces the core: SSIM at sizes 128 and 32 on 256 pairs each, largest deviation 5e-7.
* The planned **local colour difference** ([02](02-comparison-modes.md), mode 3, T11): worst 4×4-block colour RMS of area-resampled thumbnails, 32–128 px; and **aligned local colour**: the same at 64 px after aligning the two images with SIFT keypoints (below), over the part both show.
* Full-reference metrics on 256 × 256 copies: windowed SSIM (mean, and the worst 32-px tile), MS-SSIM, GMSD, HaarPSI, VIF, CIEDE2000, PSNR. Butteraugli and SSIMULACRA2 (libjxl's tools) at 512 and 1024 px.
* Colour histograms; perceptual hashes (aHash, dHash, pHash, wHash with 64 bits, pHash and dHash with 256 bits, colorhash, the crop-resistant hash); the share of SIFT keypoints left unmatched.
* SigLIP, a CLIP-like neural image embedding (Google's so400m model, a file already on the user's PC): 1 − cosine similarity.

## Which algorithm finds which kind of copy

Versions before the worst pair of the original against one kind of copy (of 2,867 version pairs; "–" = 2,000 or more, nearly every version first; best values in bold):

| Algorithm | compression | resolution | web copy | upscaled | processed | crop | overlay | greyscale | transform |
|---|---|---|---|---|---|---|---|---|---|
| SSIM, grey, bilinear, 128 (the user's setting) | 45 | 865 | 666 | 442 | 390 | – | – | **0** | – |
| SSIM, grey, area, 128 | 55 | 380 | 175 | 4 | 488 | – | – | **0** | – |
| SSIM, grey, area, 64 | 77 | 285 | 129 | 1 | 721 | – | – | **0** | – |
| mean square, grey, area, 64 | 59 | 293 | 103 | 1 | 1,156 | – | – | **0** | – |
| local colour, 64 | 1 | 97 | **1** | **0** | 136 | – | – | 1,213 | – |
| local colour, 128 | **0** | 164 | 34 | **0** | **31** | – | – | 829 | – |
| windowed SSIM, worst tile | 28 | 129 | 59 | **0** | 63 | – | – | 62 | – |
| GMSD | 1 | 554 | 213 | 4 | 45 | – | – | 1 | – |
| HaarPSI | 114 | 569 | 248 | 1 | 299 | – | – | – | – |
| Butteraugli, 512 | **0** | 59 | **1** | **0** | 95 | – | – | 1,623 | – |
| Butteraugli, 1024 | **0** | **5** | 5 | **0** | 32 | – | – | 1,471 | – |
| SSIMULACRA2, 512 | 29 | 68 | 33 | **0** | 66 | – | – | 628 | – |
| aligned local colour, 64 | 1 | 18 | **1** | **0** | 134 | **10** | **768** | 1,213 | – |
| pHash, 256 bits | 408 | 408 | 408 | 408 | 854 | – | – | 408 | – |
| colour histogram | 1,662 | 433 | 930 | 39 | 1,621 | 1,714 | 1,638 | – | **9** |
| SigLIP embedding | 539 | 920 | 919 | 328 | 83 | – | 1,999 | – | – |

* **Compression and upscaling are easy** for most metrics that compare the pictures; AntiDupl's bilinear pipeline is the exception for upscaled copies (442 versions first at the user's setting). The cheap metrics differ in **resolution**: the 12 % copies (300–480 px wide) are the farthest from the original; Butteraugli at 1024 px puts 2 versions before them, aligned local colour 18, every other metric 59 or more.
* **Local colour at 64 px** is the best of the cheap algorithms: with the threshold at the last plain copy except the 12 and 25 % ones, it pairs up **1** version (two of the artist's variants whose difference doesn't show at 512 px), against 85 for the best SSIM setting and 462 at the user's setting (next section). Butteraugli at 512 px pairs up none.
* **Processed copies** are a colour change for the colour metrics: a brightness +5 % copy puts 136 versions before it with local colour at 64 px. Grey SSIM hardly sees saturation (1–45 versions before it) but sees brightness (390–721). Whether such a copy is one to delete is the user's call; a copy that lost its colour profile looks like this.
* **Crops are found only after alignment.** The metrics that compare the pictures point by point sort crops among the versions: the median 1 % crop after 31–91 % of them, the median 5 % crop after 64–100 %. Colour histograms and SigLIP tolerate crops but can't tell versions from copies. Aligned local colour puts every crop up to 20 % per side before all but 10 versions. Overlays: the border and the corner watermark align and sort among the copies; the large centre text sorts among the versions for every metric.
* **Greyscale** sorts among the copies for grey AntiDupl settings and GMSD, and after hundreds of versions for colour metrics: the plane setting decides this user's call.
* **Mirrors and rotations** are found by AntiDupl's search for turned and mirrored copies, not by the metrics; only colour histograms ignore them.
* **Hashes and embeddings can't tell a copy from a version.** pHash, dHash, aHash, wHash and the crop-resistant hash give most minor variants and edits a distance as small as the copies' (pHash-256: 408 versions within the distance of the farthest compressed copy). SigLIP sees the same artwork, not the same picture: steps and edits score as close as copies. VIF ranks resized copies after most versions (1,835 before the 12 % copies).

## AntiDupl's own algorithms: size, grey or colour, resampling

Versions before the last plain copy, with / without the 12–25 % copies:

| Algorithm | Plane | Resampling | 16 | 32 | 64 | 128 |
|---|---|---|---|---|---|---|
| SSIM | grey | bilinear | 443 / 351 | 384 / 263 | 476 / 303 | 872 / 462 |
| SSIM | grey | area | 412 / 342 | 348 / 227 | 333 / 120 | 451 / 85 |
| SSIM | colour | bilinear | 426 / 370 | 344 / 276 | 428 / 250 | 765 / 430 |
| SSIM | colour | area | 416 / 366 | 311 / 245 | 281 / 193 | 412 / 133 |
| mean square | grey | bilinear | 348 / 288 | 320 / 232 | 407 / 236 | 760 / 350 |
| mean square | grey | area | 365 / 308 | 367 / 181 | 348 / 94 | 448 / 135 |
| mean square | colour | bilinear | 373 / 373 | 285 / 245 | 351 / 232 | 704 / 306 |
| mean square | colour | area | 442 / 442 | 341 / 273 | 294 / 220 | 434 / 127 |
| local colour | colour | area | – | 262 / 75 | **126 / 1** | 170 / 1 |

* **Area resampling beats AntiDupl's bilinear pipeline at 64 and 128 px** for both algorithms (T10); at 32 px it is mixed. The bilinear pipeline is worst at 128, the user's size: at 128 px area pairs up 85 versions where bilinear pairs up 462. Bilinear-then-halving keeps aliasing that area averaging removes; it also makes a blurred copy look far (188 versions before it at the user's setting, 1 with area) and an upscaled one (442 against 4).
* **Size 64 or 128, not 16.** With area resampling, 64 px is best when the 12–25 % copies count. Without them, SSIM gains at 128 px (85 against 120), mean square doesn't (135 against 94), and local colour is the same.
* **Grey or colour** decides the greyscale version (above). Otherwise neither wins: colour is mostly better when the 12–25 % copies count, grey when they don't.
* **Thresholds:** every SSIM setting finds every plain copy below 0.62 % (below 0.28 % without the 12–25 % copies), but AntiDupl's smallest threshold above 0 is 1 %, which at the user's setting pairs up 1,112 of the 2,867 versions (T16). Mean square needs 0.33–2.55 %. Local colour at 64 px needs 3.7 % (1.5 % without the 12–25 % copies), and 1 % misses a quarter of the plain copies.
* What the user's setting pairs up besides copies (without the 12–25 % copies): 170 of the 226 minor variants, 3 medium ones, 63 minor and 199 medium edits, 27 near-final steps. SSIM with area at 128 px: 35 minor variants and 50 minor edits. Local colour at 64 px: 1 minor variant.

## Which copy is worse

Pairs of the same picture that differ in one way, so one is known to be worse: **compression** (same size, one more lossy: a lower quality of the same codec, more re-encodings, or lossy against the original), **resolution** (lossless, one smaller), **crop** (lossless, full size, one shows less), **web copy** (the original against a smaller compressed copy), **upscaled** (the original and its shrunk-and-blown-up copies: the same pixel count, less real detail). The share of pairs where each property ranks the worse one lower (pairs where it has a value):

| Property | compression (192) | resolution (180) | crop (224) | web copy (8) | upscaled (12) |
|---|---|---|---|---|---|
| pixels | 50 % (all equal) | 100 % | 100 % | 100 % | 50 % (all equal) |
| file size | 98 % | 99 % | 96 % | 100 % | 83 % |
| bytes per pixel | 98 % | 1 % | 39 % | 100 % | 83 % |
| JPEG quality estimate (128 JPEG pairs) | 98 % | – | – | – | – |
| sharpness (Laplacian variance) | 60 % | 8 % | 31 % | 0 % | 100 % |
| detail lost when halved | 62 % | 7 % | 29 % | 0 % | 100 % |
| AntiDupl blockiness | 95 % | 56 % | 45 % | 88 % | 33 % |
| AntiDupl blurring | 38 % | 34 % | 66 % | 0 % | 100 % |
| **the rule below** | 98 % | 100 % | 100 % | 100 % | 100 % |

The rule (`better_copy` in `tools/settings_study.py`): **more pixels** is better (more than 0.5 % apart); at the same pixel count, **lossless beats lossy**; both lossless, **clearly more detail** (25 % or more) is better, which unmasks upscaled copies; both JPEG, the **higher quality estimate**; else the **larger file**. It misses only a JPEG re-encoded three times at the same quality, which the quality estimate can't tell from the one saved once and which is a slightly larger file. File size alone also misleads on upscaled copies: one illustration's are larger files than its original. The JPEG quality and bytes-per-pixel columns of [06 § S4](06-stretch-and-ameliorations.md) (A2) would show the user the same evidence.

## Crops

SIFT keypoints on 512 px copies, matched and aligned with a similarity transform (RANSAC); one image counts as a crop of the other when at least 15 matches agree, the smaller lies within the other and covers under 97 % of it.

* Every crop is found, with the share of the original it keeps estimated to two decimals of the truth (centre square, 1–20 % per side, one side, rescaled). The 90° rotation aligns too, with the angle found.
* No copy pair counts as a crop; no unrelated pair aligns at all.
* 128 version pairs count as crops: one illustration's middle steps against its final and copies. Those steps are on a canvas 3 % taller and 1 % wider than the final's, and the final shows 96 % of it: the geometry is right.
* Mirrored copies don't align (SIFT keypoints aren't mirror-symmetric); AntiDupl's mirrored search covers them.

What this needs in AntiDupl: keypoints stored per image (tens of kB each), and matching only for candidate pairs, since matching every pair of a large collection is too slow; the candidates can't come from the global metrics, which rank crops among the versions. [06 § S4](06-stretch-and-ameliorations.md) A5 has the idea; a copy-detection embedding (SSCD, below) is a candidate for finding them.

## Conclusions

* **T10:** area resampling for every algorithm's reduced images.
* **T11:** local colour difference at 64 px as the default: the best cheap algorithm for every plain copy, compression and upscaling included.
* **T12:** Butteraugli as a slow second look at the candidates, at 512 px (1024 px for copies under a quarter of the size).
* **Crops** need alignment, so a new kind of search (above).
* The worse copy: the rule above, when hints are reworked ([06 § S4](06-stretch-and-ameliorations.md) A3).

## Candidates not tested yet

The candidates below need downloads (the user's call); the PyTorch ones need only their model files, as the user's PC has PyTorch already.

| Candidate | What it might add | Download |
|---|---|---|
| SSCD (Meta's copy-detection descriptor) | trained to match copies through crops, overlays and compression: candidates for crop detection | model file, 99 MB |
| DINOv2 ViT-S/14 | instance-level embedding, closer to "same picture" than CLIP-like ones | model file, 88 MB |
| LPIPS (AlexNet) | learned full-reference difference | AlexNet weights 244 MB, `lpips` package |
| DISTS | learned difference that tolerates texture resampling | VGG16 weights 553 MB, `DISTS-pytorch` package |
| OpenCV contrib | ORB and AKAZE keypoints (faster than SIFT, available to C++ through vcpkg), more hashes (block mean, Marr–Hildreth, radial variance, colour moments) | `opencv-contrib-python`, 54 MB |
| PDQ (Meta's 256-bit hash) | the common standard for matching reposts; expected to behave like pHash-256 | `pdqhash` (no wheel for Python 3.14: a source build) |

## Limits and growing the set

* Four illustrations by one artist, digital painting with PNG originals. Other artists and styles (photos, pixel art, line art, 3D renders) may move the sizes and thresholds; the user names more folders (T14).
* The copies are made here; real reposts combine several differences (a crop of a smaller JPEG with a watermark). The decision log of the personal build (T17) collects the pairs where the user's decision goes against the difference: explained and named by the kind of difference, they join the set.

## Tools

`tools/study_set.py` builds or extends the set from a config naming archive files (the config stays outside this repository: it names files in the user's archive), `tools/settings_study.py` computes every metric of `tools/study_metrics.py` on every pair and writes the tables of `summary.md` (`--analysis-only` redoes them from the saved values), `tools/embed_metrics.py` adds neural embeddings; see [tools/README.md](tools/README.md).
