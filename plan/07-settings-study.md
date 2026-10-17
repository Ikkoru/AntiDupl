# 07 — Settings study: which algorithm and setting for which kind of difference

Which comparison algorithm, reduced size, grey or colour, and resampling find the copies of a picture (to delete) without pairing up its versions (to keep), for each kind of difference: compression, lower resolution, upscaling, crops and so on; and which property of the files tells the worse copy, also when a copy was converted again after a lossy step. Measured on a sample set built from the user's archive. The raw numbers are on the user's PC (workspace `Research\results\`: `summary.md` holds every table, also those not repeated here), rebuilt by the tools at the end.

## The set

Four digital illustrations by one artist (2470–4000 px wide, PNG), each with:

| Kind | Per illustration |
|---|---|
| original | the artist's final image |
| variant | the artist's other versions (13, 9, 2 and 0): local changes from under 0.1 % of the picture to most of it |
| step | 8–10 work-in-progress pictures, sketch to near-final; one illustration's steps are on a slightly larger canvas than its final |
| copy: compression | JPEG q100 and q95 (4:4:4), q90 down to q30 (4:2:0), q85 re-encoded three times; WebP q90/75/50; AVIF q60; JPEG XL distance 1 and 4 |
| copy: lossy history | converted again after a lossy step: JPEG q60 saved as PNG; the same with 3 px cut from the left and top; JPEG q45 re-saved as JPEG q95; JPEG q85 re-saved as WebP q80; WebP q50 saved as PNG |
| copy: resolution | 90, 75, 50, 33, 25 and 12 % (Lanczos, PNG); 50 % bilinear and nearest neighbour |
| copy: web | 50 % as JPEG q85 and q60; 25 % as JPEG q75, q60 and q45; 12 % as JPEG q60 (the q60 and q45 ones also serve the jpegQS check below) |
| copy: upscaled | shrunk to 50 % and 25 %, then blown back up to full size |
| copy: processed | sharpened, blurred (1 px), brightness +5 %, saturation +15 % |
| crop | 1, 2, 5, 10, 20 % cut from each side; 10 % from one side; the centre square; 5 % cut, then resized back to full size |
| overlay | a white border; a small watermark in a corner; large semi-transparent text across the middle |
| greyscale, transform | greyscale; mirrored; rotated 90° |
| edit | small text; a black bar; mosaic; a smudged region; a cloned patch; a local recolour (all on the most detailed regions); a global recolour |

Every pair within an illustration is compared, and each final image against every image of the other three: 306 images, 12,512 pairs.

| Class | Pairs |
|---|---|
| copy: the original and its copies, any two | 3,280, of which 2,520 **plain** (no processed copy and not the 3 px cut one in the pair) |
| variant-minor, -medium, -major: the original or a copy against a variant, or two variants; under 1 %, 1–5 %, 5 % or more of the picture changed | 280, 230, 589 |
| sketch, wip-far, wip-close: the original or a copy against a step in the first quarter, middle, last quarter of the steps | 328, 697, 369 |
| edit-minor (text, bar), edit-medium (mosaic, smudge, clone, local recolour), edit-major (global recolour) | 328, 656, 164 |
| crop, overlay, greyscale, transform: the user's call whether these are copies | 1,312, 492, 164, 328 |
| unrelated: a final against another illustration's image | 912 |
| other (step~step, variant~edit, …): not judged | 2,383 |

The versions (variant, step and edit classes) add up to 3,641 pairs.

## Method

Every algorithm gives each pair a value; sorted by it, smallest first, the results come in the order the user works through them. The measure is **versions before the last copy**: how many version pairs come before the last copy pair, so how many versions the user has to look at (and mark as mistakes) before having seen every copy. A threshold set just high enough to find every copy pairs up exactly those versions. **AUC** in `summary.md`: the chance that a copy pair comes before a version pair.

Algorithms, all as a difference (0 = identical):

* AntiDupl's SSIM and mean square difference at every setting: size 16–128; grey (AntiDupl's plane) or colour (the same per B, G, R plane); *bilinear* (AntiDupl's resampling: bilinear to 256, then 2×2 reductions) or *area* (box filter straight to the size, [01 § G](01-difference-correctness.md)). The Python pipeline (`tools/adsim.py`) reproduces the core: SSIM at sizes 128 and 32 on 256 pairs each, largest deviation 5e-7.
* The **local colour difference** ([02](02-comparison-modes.md), mode 3, T11): worst 4×4-block colour RMS of area-resampled thumbnails, 32–128 px; and **aligned local colour**: the same at 64 px after aligning the two images with keypoints (SIFT; ORB and AKAZE through OpenCV), over the part both show. The core's own (the personal branch, 64 px) agrees with the study's on every pair within an illustration that it reports under 50 % (`core_search.py`; Spearman 0.98, median difference 0.03 points) and pairs up the same versions before the last plain copy.
* Full-reference metrics on 256 × 256 copies: windowed SSIM (mean, and the worst 32-px tile), MS-SSIM, GMSD, HaarPSI, VIF, CIEDE2000, PSNR, and the learned LPIPS (AlexNet) and DISTS. Butteraugli and SSIMULACRA2 (libjxl's tools) at 512 and 1024 px.
* Colour histograms; perceptual hashes (aHash, dHash, pHash, wHash with 64 bits, pHash and dHash with 256 bits, colorhash, the crop-resistant hash, OpenCV's block mean, Marr–Hildreth, radial variance and colour moment hashes); the share of keypoints left unmatched.
* Neural image embeddings, 1 − cosine similarity: SigLIP (a CLIP-like model), DINOv2 ViT-S/14, and SSCD (Meta's model trained for copy detection).
* For the worse copy, also per image: the JPEG trace in the pixels (below), and no-reference quality scores: the learned TOPIQ-NR and MUSIQ (trained on KonIQ-10k ratings), NIQE and BRISQUE.

## Which algorithm finds which kind of copy

Versions before the worst pair of the original against one kind of copy (of 3,641 version pairs; "–" = 2,000 or more, nearly every version first; the best value of each column in bold; *shifted* is the JPEG q60 saved as PNG with 3 px cut from two sides):

| Algorithm | compression | resolution | web copy | upscaled | processed | shifted | crop | overlay | greyscale | transform |
|---|---|---|---|---|---|---|---|---|---|---|
| SSIM, grey, bilinear, 128 (the user's setting) | 53 | 1,069 | 1,156 | 528 | 465 | 1,373 | – | – | **0** | – |
| SSIM, grey, area, 128 | 63 | 470 | 545 | 4 | 614 | 455 | – | – | **0** | – |
| SSIM, grey, area, 64 | 88 | 353 | 359 | 1 | 913 | 350 | – | – | **0** | – |
| mean square, grey, area, 64 | 68 | 362 | 383 | 1 | 1,462 | 384 | – | – | **0** | – |
| local colour, 64 | 1 | 120 | 166 | **0** | 172 | **121** | – | – | 1,537 | – |
| local colour, 128 | **0** | 206 | 209 | **0** | **39** | 211 | – | – | 1,054 | – |
| windowed SSIM, worst tile | 33 | 161 | 275 | **0** | 75 | 356 | – | – | 74 | – |
| GMSD | 1 | 682 | 1,340 | 4 | 54 | 951 | – | – | 1 | – |
| HaarPSI | 132 | 685 | 934 | 1 | 354 | 690 | – | – | – | – |
| Butteraugli, 512 | **0** | 76 | 82 | **0** | 122 | 137 | – | – | – | – |
| Butteraugli, 1024 | **0** | **9** | **40** | **0** | 40 | 342 | – | – | 1,865 | – |
| SSIMULACRA2, 512 | 34 | 84 | 209 | **0** | 80 | 228 | – | – | 796 | – |
| LPIPS (AlexNet) | 122 | 678 | 1,145 | 16 | 154 | 498 | – | – | – | – |
| DISTS | 637 | 642 | – | 10 | 686 | 605 | – | – | – | – |
| aligned local colour, 64 (SIFT) | 1 | 20 | **40** | **0** | 169 | 301 | **11** | **975** | 1,537 | – |
| aligned local colour, 64 (ORB) | 1 | 199 | 172 | **0** | 168 | 125 | 81 | **975** | 1,537 | – |
| aligned local colour, 64 (AKAZE) | 1 | 80 | 80 | **0** | 168 | 133 | 128 | **975** | 1,537 | – |
| pHash, 256 bits | 516 | 516 | 516 | 516 | 1,082 | 819 | – | – | 516 | – |
| radial variance hash (OpenCV) | 583 | 720 | 748 | 236 | 1,214 | 739 | – | – | 81 | – |
| colour histogram | – | 437 | 1,853 | 39 | – | 1,125 | – | – | – | **9** |
| SSCD embedding | 918 | 463 | – | 8 | 216 | 1,252 | – | – | – | – |
| DINOv2 embedding | 752 | 321 | – | 11 | 113 | 423 | – | – | – | – |
| SigLIP embedding | 620 | 1,060 | 1,059 | 366 | 89 | 255 | – | – | – | – |

SigLIP has no values for the 50 % q60, 25 % q60 and q45, and 12 % q60 JPEGs (its model file is missing from the PC), so its web copy column covers only the 50 % q85 and 25 % q75 copies.

* **Compression and upscaling are easy** for most metrics that compare the pictures; AntiDupl's bilinear pipeline is the exception for upscaled copies (528 versions first at the user's setting). The copies converted after a lossy step count as compression here.
* The cheap metrics differ in **resolution**: the 12 % copies (300–480 px wide) are the farthest from the original, and a JPEG of them farther still. Butteraugli at 1024 px (either norm) puts 9 versions before the resized copies and 35–40 before the web copies, aligned local colour (SIFT) 20 and 40, every other metric 76 or more.
* **Local colour at 64 px** is the best of the cheap algorithms: with the threshold at the last plain copy except the 12 and 25 % ones, it pairs up **1** version (two of the artist's variants whose difference doesn't show at 512 px), against 101 for the best SSIM setting and 552 at the user's setting (next section). Butteraugli at 512 px pairs up none.
* **Processed copies** are a colour change for the colour metrics: a brightness +5 % copy puts 172 versions before it with local colour at 64 px. Grey SSIM hardly sees saturation (1–50 versions before it) but sees brightness (465–913). Whether such a copy is one to delete is the user's call; a copy that lost its colour profile looks like this.
* **A 3 px cut** (the *shifted* copy) puts over 100 versions first even for the best metrics, the aligned ones included.
* **Crops are found only after alignment.** The metrics that compare the pictures point by point sort crops among the versions: the median 1 % crop after 27–91 % of them, the median 5 % crop after 64–100 %. Colour histograms and the embeddings tolerate crops but can't tell versions from copies. Aligned local colour with SIFT puts every crop up to 20 % per side before all but 11 versions (ORB 81, AKAZE 128). Overlays: the border and the corner watermark align and sort among the copies; the large centre text sorts among the versions for every metric.
* **Greyscale** sorts among the copies for grey AntiDupl settings and GMSD, and after 1,000 or more versions for the colour metrics: the plane setting decides this user's call.
* **Mirrors and rotations** are found by AntiDupl's search for turned and mirrored copies, not by the metrics; only colour histograms and OpenCV's colour moment hash ignore them.
* **Hashes and embeddings can't tell a copy from a version.** The perceptual hashes (imagehash's and OpenCV's) give most minor variants and edits a distance as small as the copies' (pHash-256: 516 versions within the distance of the farthest compressed copy). The embeddings see the same artwork, not the same picture: steps and edits score as close as copies, SSCD's too, since it was trained to ignore edits. The learned full-reference metrics put 122 (LPIPS, compression) to 678 versions (LPIPS, resolution) before the farthest compressed or resized copy. VIF ranks resized copies after most versions (2,258 before the 12 % copies).

## AntiDupl's own algorithms: size, grey or colour, resampling

Versions before the last plain copy, with / without the 12–25 % copies:

| Algorithm | Plane | Resampling | 16 | 32 | 64 | 128 |
|---|---|---|---|---|---|---|
| SSIM | grey | bilinear | 564 / 431 | 526 / 322 | 632 / 364 | 1,157 / 552 |
| SSIM | grey | area | 526 / 427 | 445 / 278 | 432 / 144 | 573 / 101 |
| SSIM | colour | bilinear | 540 / 465 | 446 / 337 | 684 / 301 | 994 / 510 |
| SSIM | colour | area | 578 / 462 | 452 / 306 | 480 / 228 | 731 / 154 |
| mean square | grey | bilinear | 440 / 352 | 398 / 278 | 527 / 278 | 947 / 417 |
| mean square | grey | area | 464 / 379 | 478 / 219 | 441 / 108 | 630 / 160 |
| mean square | colour | bilinear | 471 / 471 | 404 / 294 | 530 / 273 | 916 / 359 |
| mean square | colour | area | 557 / 557 | 514 / 340 | 541 / 260 | 851 / 147 |
| local colour | colour | area | – | 372 / 92 | **169 / 1** | 251 / 1 |

* **Area resampling beats AntiDupl's bilinear pipeline at 128 px** for both algorithms (T10), and at 64 px but for mean square in colour with the 12–25 % copies (541 against 530); at 32 px it is mixed. The bilinear pipeline is worst at 128, the user's size: at 128 px area pairs up 101 versions where bilinear pairs up 552. Bilinear-then-halving keeps aliasing that area averaging removes; it also makes a blurred copy look far (221 versions before it at the user's setting, 1 with area) and an upscaled one (528 against 4).
* **Size 64 or 128, not 16.** With area resampling and the 12–25 % copies counted, 64 px is best in grey and for local colour; in colour, 32 px is better by under 30 versions. Without them, SSIM gains at 128 px (101 against 144), mean square doesn't (160 against 108), and local colour is the same.
* **Grey or colour** decides the greyscale version (above). Otherwise grey is mostly better: with area resampling at every size, with or without the 12–25 % copies (but for mean square at 128 px without them, 160 against 147); with bilinear resampling it depends on the size.
* **Thresholds:** every SSIM setting from 32 px up finds every plain copy below 0.75 % (below 0.28 % without the 12–25 % copies), but AntiDupl's smallest threshold above 0 is 1 %, which at the user's setting pairs up 1,386 of the 3,641 versions (T16). Mean square needs 0.69–2.80 % (0.33–1.72 % without them). Local colour at 64 px needs 4.1 % (1.5 % without them), and 1 % misses nearly a third of the plain copies. At 4 %, the core's default, the study's values pair up 169 versions and miss 3 of the 2,520 plain copy pairs, each the 12 % q60 JPEG against a 25 % copy of one illustration, both of which pair up with the original; the original against its brightness +5 % copy comes at 3.9–4.4 %, around it (5 %: no plain copy missed, 220 versions).
* What the user's setting pairs up besides copies (without the 12–25 % copies): 202 of the 280 minor variants, 3 medium ones, 77 minor and 238 medium edits, 32 near-final steps. SSIM with area at 128 px: 42 minor variants and 59 minor edits. Local colour at 64 px: 1 minor variant.

## Which copy is worse

Pairs of the same picture that differ in one way, so one is known to be worse: **compression** (same size, one more lossy: a lower quality of the same codec, more re-encodings, or lossy against the original), **resolution** (lossless, one smaller), **crop** (lossless, full size, one shows less), **web copy** (the original against a smaller compressed copy), **upscaled** (the original and its shrunk-and-blown-up copies: the same pixel count, less real detail), **lossy history** (each copy converted again after a lossy step against files known to be better: the original, the JPEG or WebP it came from, a JPEG of a higher quality; `HISTORY_PAIRS` in `tools/settings_study.py`). The share of pairs where each property ranks the worse one lower (pairs where it has a value):

| Property | compression (192) | resolution (180) | crop (224) | web copy (24) | upscaled (12) | lossy history (52) |
|---|---|---|---|---|---|---|
| pixels | 50 % (all equal) | 100 % | 100 % | 100 % | 50 % (all equal) | 58 % |
| file size | 98 % | 99 % | 96 % | 100 % | 83 % | 35 % |
| bytes per pixel | 98 % | 1 % | 39 % | 100 % | 83 % | 35 % |
| JPEG quality of the file's table | 98 % (JPEG pairs) | – | – | – | – | 0 % (12 pairs) |
| JPEG trace in the pixels | 96 % (68) | – | – | – | – | 88 % (24) |
| effective JPEG quality (the lower of both; 100 for lossless without a trace) | 97 % | 50 % | 50 % | 100 % | 50 % | 86 % (36) |
| sharpness (Laplacian variance) | 60 % | 8 % | 31 % | 0 % | 100 % | 92 % |
| detail lost when halved | 62 % | 7 % | 29 % | 0 % | 100 % | 81 % |
| AntiDupl blockiness | 95 % | 56 % | 45 % | 96 % | 33 % | 85 % |
| AntiDupl blurring | 38 % | 34 % | 66 % | 0 % | 100 % | 63 % |
| TOPIQ-NR (learned, no-reference) | 96 % | 5 % | 47 % | 33 % | 100 % | 94 % |
| MUSIQ (learned, no-reference) | 92 % | 15 % | 33 % | 42 % | 100 % | 98 % |
| NIQE (no-reference) | 65 % | 26 % | 33 % | 8 % | 67 % | 71 % |
| BRISQUE (no-reference) | 45 % | 6 % | 48 % | 0 % | 42 % | 31 % |
| **the rule**, the file's format and JPEG table only | 100 % | 100 % | 100 % | 100 % | 100 % | 33 % |
| **the rule** with the JPEG trace | 100 % | 100 % | 100 % | 100 % | 100 % | 83 % |
| **the rule** with the JPEG trace and TOPIQ-NR deciding ties | 100 % | 100 % | 100 % | 100 % | 100 % | 96 % |

The no-reference scores are taken on a central 1024 px crop at full size, where compression shows; between sizes (resolution, crops, web copies) they compare different amounts of the picture and mean nothing.

**The rule** (`better_copy` in `tools/settings_study.py`): **more pixels** is better (more than 0.5 % apart); else the higher **effective JPEG quality** (more than 2 apart); at the same quality, both lossless, **clearly more detail** (25 % or more; it unmasks upscaled copies) and then the larger file; at the same lossy quality the **smaller file**, the one converted fewer times (a JPEG re-saved three times at q85 is a slightly larger file than the one saved once); a lossless file over one whose quality can't be read (WebP, AVIF, JPEG XL); else the larger file.

**Lossy history.** A JPEG saved as PNG, or a q45 JPEG re-saved at q95, carries a lossless format or a high quality setting while showing the losses of the first save, and the file's own format and table pick it over better files (33 % right). The pixels still show the first save: a JPEG rounds each 8 × 8 block's DCT coefficients to multiples of its quantisation steps, and decoding or re-saving at a finer step keeps them near those multiples (Fan and de Queiroz 2003). `jpeg_history` in `tools/study_metrics.py` finds the block grid from the pixels (it survives a crop that shifts it), finds per coefficient position the largest step the coefficients cluster on, and gives the IJG quality whose table has those steps: the strongest JPEG compression the pixels went through, whatever the format now. On every JPEG step in the set, q30 to q90, as JPEG, as PNG, shifted by 3 px, or re-saved at q95, it reads the quality within 2.2; it finds no trace in any file without a JPEG step; a q95 or q100 JPEG leaves too fine a trace (its file's table says so anyway). It takes about 0.4 s per image on a central 1536 px crop. With it, the rule gets 83 % of the lossy-history pairs right, and still all the others.

**What it can't see: a lossy step that isn't JPEG.** All 9 pairs the rule still gets wrong are the PNG made from a WebP q50 file, against the q75 and q90 WebP copies (and, in one illustration, against the original, whose PNG is the smaller file): it looks like a clean lossless file. A JPEG re-saved as WebP also loses its JPEG trace. WebP (like AVIF) codes the difference from a prediction out of neighbouring pixels and smooths block edges afterwards, so its pixels keep no grid of steps to read, and the grid of its 4 px blocks that does show is often too weak (below). Two ways round it:

* **A learned quality score as the tie-breaker.** Where the effective JPEG quality doesn't decide (it is unknown for one file, or the same for both), TOPIQ-NR decides when the two scores differ by more than 0.02: the rule then gets 50 of the 52 lossy-history pairs right and still every other pair; the two misses are q75 WebP against the PNG of the q50 one. The margin was chosen on this set (from 0.03 up fewer lossy-history pairs are fixed; at 0.01 and below compression pairs break), so it needs checking on the next sets. MUSIQ ranks as well as an indicator but makes a worse tie-breaker; NIQE and BRISQUE are weak. TOPIQ is a ResNet-50 network (181 MB): fine for the study, heavy for AntiDupl.
* **A WebP trace found by re-encoding.** Re-saving a picture as WebP at each quality and measuring the change, a file that was WebP at quality Q changes little for every quality from Q up (the q50 one: 1.6 → 1.5 RMS from q55 to q75), while a picture never saved as WebP keeps changing (the original: 2.6 → 2.3). Calibrated with `tools/webp_trace.py`, and not reliable enough to join the rule. Its samples: from each of the set's 62 pictures never saved as WebP (originals, variants, steps), a 1024 px square as WebP at q20–95 (libwebp through Pillow at methods 4 and 6, and with sharp YUV through ImageMagick; no `cwebp` on the PC, the same libwebp), as JPEG→WebP and WebP→JPEG chains, and as never-WebP copies (the picture, JPEG q30–95, AVIF, JPEG XL, resized, upscaled, sharpened, blurred): 2,976 samples, 992 of them never WebP. Each detector's threshold is the highest never-WebP score of the other three illustrations, one illustration left out at a time:
  * The change curve, as a detector (the step ratios against the never-WebP median: a WebP at Q drops more than usual into Q, then stays flatter): 24 of the 992 never-WebP samples get a trace, and it finds 4–37 % of the WebP files. Single curves are far noisier than their medians.
  * Given that a file is a WebP, the curve tells its quality within 5 for 81–95 % of the files from q20 to q85 (Pillow, method 4; 57–98 % for the other two settings); at q90–95 only 5–51 %.
  * VP8's 4 px blocks also leave a grid in the pixels: the mean luma step at both 4 px edges of each 8 px period rises (3|4 and 7|0; JPEG raises only 7|0). Measured phase-free from the step profile's Fourier magnitudes, it finds 56–69 % of the WebP files from q75 up and 20–34 % below, without a false trace but on 8 JPEG q30 copies (one illustration) and one JPEG XL. A WebP q50 saved again as JPEG keeps it rarely (3–23 %).
  * Neither meets the acceptance (no trace on a never-WebP file, since a false one makes the rule prefer a worse file; the quality within about 5; the failing pairs here right). Next: a trace in the transform domain, as the JPEG one: VP8's 4×4 coefficients lie on multiples of its quantiser steps where the loop filter left them (textured regions) and the prediction can be undone; then real WebP files from the archive whose source quality is known. The macroblock grid also moves with a crop, which the calibration hasn't covered.

**jpegQS.** QuantSmooth recovers precision from a JPEG's coefficients within its quantisation steps, so the better copy of a JPEG is also the one jpegQS improves most. Run on the set's JPEG copies, full size and reduced (default `-q 3`, and `-q 6`, 3 iterations; SSIMULACRA2 and Butteraugli's 3-norm against the picture before JPEG, the original or the PNG of the same reduction, on a central crop of at most 1024 px; `tools/qs_check.py`):

* First-save JPEGs from q45 to q90 gain a median 1.1 points with `-q 3` and 1.6 with `-q 6`, at most 3.3; a few lose up to 1. Nothing at q100; at q30 `-q 3` loses up to 3 points in two of the four illustrations, `-q 6` gains up to 3. A gain of that size lifts a q60 file to about q65: here it never reorders copies 10 or more quality apart.
* **Reduced copies gain about twice as much** (the 8 × 8 blocks cover more of the picture): the 50, 25 and 12 % JPEGs at q45–q75 gain 2.4–5.0 points with `-q 6` (about 3.6 typical; full size at q60: 1.5–3.3), and Butteraugli's 3-norm drops 7–18 % at 25 % q60 against 1–10 % at full size (one full-size case rises 4 %). A 25 % q60 file then comes within 1.2–3.8 points of the 25 % q75 one, still below it. The user sees much more than these numbers: both measures were built to score compression at full quality, and may undervalue what jpegQS removes, the block edges and ringing.
* The q45 file re-saved at q95 gains nothing (0.0–0.2): jpegQS can only undo the last save, as its README says. Re-saving at the same quality (q85 three times) keeps most of the gain.
* The PNG of a q60 JPEG, re-encoded at q60 with the same encoder, gives back the JPEG's coefficients almost exactly (0.1–1.6 % of pixels differ, by chroma rounding), and jpegQS gains on it within 0.8 points of the original JPEG: the PNG hasn't lost the jpegQS option, given the quality read from its trace and the encoder's tables.

So which JPEG gains most can be predicted without running it: the gain comes from the file's own table (the coarser, the more, down to about q45) and grows as the picture gets smaller, and nothing comes back from an earlier, stronger save that the JPEG trace still shows. A file whose trace is stronger than its table has already lost what jpegQS could give back: the rule's effective quality (the lower of the two) ranks it right. For the other lossy formats there is no such tool: WebP, AVIF, HEIC and JPEG XL's own lossy mode filter block edges while decoding, so the decoded picture is already smoothed, and the AI artifact removers that work on any picture invent detail instead of staying within the file's steps. The exception is a JPEG XL made from a JPEG by lossless transcoding (`cjxl`'s default for JPEG input): it decodes back to the identical JPEG file (checked on the q60 copy; the JPEG XL is 23 % smaller), so jpegQS applies to it unchanged.

## Crops

Keypoints on 512 px copies (SIFT with scikit-image; ORB and AKAZE with OpenCV), matched and aligned with a similarity transform (RANSAC); one image counts as a crop of the other when at least 15 matches agree, the smaller lies within the other and covers under 97 % of it.

| Keypoints | original~crop judged a crop | copy pairs | version pairs | unrelated | extract (per image) | stored (per image) | match and fit (per pair) |
|---|---|---|---|---|---|---|---|
| SIFT (scikit-image) | 32 of 32 | 0 | 164 (5 %) | 0 | 310 ms | 82 kB | 21 ms |
| ORB (OpenCV, up to 1000) | 32 of 32 | 0 | 159 (4 %) | 0 | 3 ms | 38 kB | 1.4 ms |
| AKAZE (OpenCV) | 32 of 32 | 0 | 123 (3 %) | 0 | 12 ms | 33 kB | 0.7 ms |

* Every crop is found, with the share of the original it keeps estimated to two decimals of the truth (centre square, 1–20 % per side, one side, rescaled). The 90° rotation aligns too, with the angle found. Mirrored copies don't align (keypoints aren't mirror-symmetric); AntiDupl's mirrored search covers them.
* The version pairs judged crops are one illustration's middle steps against its final and copies (with ORB also 8 pairs of another illustration's steps): those steps are on a canvas 3 % taller and 1 % wider than the final's, and the final shows 96 % of it. The geometry is right.
* ORB and AKAZE judge crops as well as SIFT and are 25–100 times faster to extract here (scikit-image's SIFT is slow; OpenCV's would be closer). As the aligned comparison, SIFT keeps more crops ahead of the versions (11 versions first, ORB 81, AKAZE 128).

Matching every pair of a large collection is too slow even at 1 ms, so a crop search needs candidates first, and the global metrics can't give them (they rank crops among the versions). What only has to separate crops from **unrelated** pictures does: SSCD, SigLIP and colour histograms put every crop ahead of every unrelated pair, DINOv2 all but 3 of 912 (crops and versions alike pass, and the aligned comparison then tells them apart). The unrelated pairs here are only 912, between four illustrations by one artist; a real collection holds far more, which histograms with their 512 numbers per image will mistake more often than an embedding trained for copies. [06 § S4](06-stretch-and-ameliorations.md) A5 has the idea; this is its design: an SSCD-like embedding or histogram per image to pick candidates, ORB keypoints per image to align them, local colour on the overlap to judge.

## Conclusions

* **With upstream's build** (grey, bilinear; SSIM or mean square; whole-percent thresholds): SSIM at 32 px sorts copies before versions best (AUC 0.956, against 0.930 at 128 px) and at 1 % returns every copy; mean square returns fewer versions at 1–2 % but misses processed copies.
* **T10** (done on the personal branch): area resampling for every algorithm's reduced images.
* **T11** (done on the personal branch, threshold default 4 %): local colour difference at 64 px: the best cheap algorithm for every plain copy, compression and upscaling included.
* **T12:** Butteraugli as a slow second look at the candidates, at 512 px (1024 px for copies under a quarter of the size).
* **Crops** (T19): a new kind of search in two stages (above).
* **The worse copy:** the rule above with the JPEG trace, when hints are reworked ([06 § S4](06-stretch-and-ameliorations.md) A3); the JPEG quality, its trace and bytes per pixel as columns (A2) would show the user the same evidence. For lossy steps that aren't JPEG: a learned score such as TOPIQ-NR as the tie-breaker; the WebP trace by re-encoding fell short in its calibration (above).
* Hashes, embeddings (SSCD, DINOv2, SigLIP) and the learned full-reference metrics (LPIPS, DISTS) are no help in telling copies from versions; the embeddings are the candidate finders for crops.

## Candidates not tested yet

| Candidate | What it might add | Needs |
|---|---|---|
| WebP history in the transform domain: VP8's 4×4 coefficients on its quantiser steps (above) | the lossy steps the JPEG trace can't see | research; the re-encoding curve and the pixel grid fell short |
| a keypoint index (ORB descriptors in an inverted file or hash tables) | crop candidates without an embedding | design work |

## Limits and growing the set

* Four illustrations by one artist, digital painting with PNG originals. Other artists and styles (photos, pixel art, line art, 3D renders) may move the sizes and thresholds; the user names more folders (T14).
* The copies are made here; real reposts combine several differences (a crop of a smaller JPEG with a watermark). The decision log of the user's everyday AntiDupl (T17, T18) collects the pairs where the user's decision goes against the difference: explained and named by the kind of difference, they join the set.

## Tools

`tools/study_set.py` builds or extends the set from a config naming archive files (the config stays outside this repository: it names files in the user's archive), `tools/settings_study.py` computes every metric of `tools/study_metrics.py` on every pair and writes the tables of `summary.md` (`--analysis-only` redoes them from the saved values), `tools/embed_metrics.py` adds the neural metrics and the no-reference scores, `tools/qs_check.py` measures jpegQS on the JPEG copies, `tools/webp_reencode.py` prints the WebP re-encoding curves of given files, `tools/webp_trace.py` makes and measures the WebP trace's calibration samples (`--analyze` gives the figures above); see [tools/README.md](tools/README.md).
