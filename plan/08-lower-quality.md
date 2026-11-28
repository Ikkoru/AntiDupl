# 08 — Recognising the lower-quality copy: upscales, JPEG restoration, lossy history

For the PR "Recognition of lower quality" (T37 with T40, T40a and T40b): what AntiDupl could show about a pair beyond its pixel count and file size, so that the user's eye goes where it pays. A blown-up copy has more pixels and no more picture (T37). A JPEG can be partly restored by jpegQS, and how far is a property of the file (T40). Other lossy formats have no such tool (T40a). A PNG made from a JPEG can still be restored, if the JPEG can be rebuilt from its pixels (T40b). [07 § Which copy is worse](07-settings-study.md#which-copy-is-worse) is the background: `better_copy`'s rule, the JPEG trace in the pixels (`jpeg_history`), `line_detail`, and the first jpegQS measurements.

The sets: the study's four illustrations ([07 § The set](07-settings-study.md#the-set)), copies made from their originals by the tools named in each section, and the user's real runs where they hold pairs the user judged (the workspace's `Research\real-runs\`). The raw tables are in the workspace's `Research\results\lower-quality\`.

## Methods published since the study

Searched 2026-11-28 for each topic; what the search turned up, and what was tried.

| Topic | Method | Kind | Here |
|---|---|---|---|
| Upscale detection | [resdet](https://github.com/0x09/resdet): the source resolution, from zero crossings in rows' and columns' DCT spectra | single image, gives the size | measured below |
| | [getnative](https://github.com/Infiziert90/getnative): descales with a kernel at each height, the error dips at the native one | single image, gives the size, for anime | not run: it reads stills only through VapourSynth's `imwri` plugin, not installed; the targeted resdet question covers its use |
| | [ird](https://github.com/li-yanhao/ird) (Li et al., T-PAMI 2026): resampling as correlations in the Fourier spectrum, an a contrario test bounding false alarms; claims robustness to JPEG and AI interpolators | single image; reports the distances where resampling shows, the source size being the size less the distance | measured below with its rank-transform preprocessing (its TV preprocessing, meant for JPEGs, is a C program needing libpng and libtiff, not built here) |
| | AI upscalers: waifu2x (CUNet), Real-ESRGAN (`x4plus-anime`, `animevideov3`), Real-CUGAN | samples to test the detectors on | measured below |
| | eigenvalues of autocorrelation matrices; learned detectors for video super-resolution | single image | not tried: no released tools for stills |
| JPEG restoration within the file | [jpegQS](https://github.com/ilyakurdyukov/jpeg-quantsmooth) (installed): smoothing kept inside each coefficient's rounding interval | constrained | measured below |
| | [knusperli](https://github.com/google/knusperli): picks each coefficient inside its interval to make block edges continuous | constrained, deblocking only | not tried: libjpeg-turbo's maintainers measured it against their decoder (its issue #558) and it lost on most images by DSSIM; it builds with Bazel |
| | [jpeg2png](https://github.com/victorvde/jpeg2png): the smoothest picture (total generalised variation) that re-encodes to the same JPEG | constrained, for drawings ("images that should never be saved as JPEG", its README); overblurs photos | measured below (1.01) |
| | learned decoders and artifact removers: FBCNN, QGAC (the quantisation table as input), JDEC (CVPR 2024), JPNeO (ICCV 2025) | free: they invent detail unless their output is projected back into the file's intervals | not tried; such a projection would make any of them a constrained restorer |
| Other formats | JPEG XL's lossy decoder clamps its edge-preserving filter to the quantisation intervals itself; AV1 (AVIF) and HEVC (HEIC) filter in the loop; WebP's decoder can dither chroma (`dwebp -dither`, smooth areas only, against banding) | built into decoders | nothing to add on top |
| | colour dequantisation of GIFs (GIF2Video, CVPR 2019) | learned, invents | not tried |
| Lossy history | JPEG quantisation-table estimation from pixels: Fan and de Queiroz 2003, a factor-histogram method (2015), the IPOL 2022 estimator with confidence per entry | reads the tables | built on below: tables read and checked by decoding again |

## Upscaled copies (T37)

`upscale_grid.py` makes, from each illustration, a smaller copy and a larger one: either the genuine larger reduction of the original, or the smaller blown up 1.25× to 4× by a known kernel (nearest, bilinear, bicubic, Mitchell, Lanczos, Lanczos then sharpened), as PNG or saved again as JPEG q90 and q75 (360 upscales, 60 genuine). Two tests per pair: `line_detail`, and one question put to resdet about the larger image alone: does any of its detections name the smaller's width or height, within 2 %? Asked blind, resdet reports something for 45 of the 60 genuine copies (confidence up to 0.57); asked that question, none.

| Larger copy | `line_detail` (under 0.865 = blown up) | resdet at the smaller's size |
|---|---|---|
| genuine | 0.94–0.99: none flagged | none |
| bilinear, bicubic, Mitchell, Lanczos | 0.48–0.78: all flagged | all, confidence 0.66–1.00 |
| nearest | 0.59–0.93: not at 1.25× and 1.5× | all but two (1.25× as JPEG), 0.56–1.00 |
| Lanczos, then sharpened | 0.98–1.48: none flagged | all, 0.66–0.78 |

So the two see different upscales: `line_detail` misses the ones that are not softer on their lines, resdet catches those, and either test alone flags no genuine copy. Together they flag 359 of the 360.

On the Tumblr run's pairs the user judged (`upscale_check.py --resdet`), `line_detail` flags all 9 the user confirmed as upscales (0.61–0.83) and none of the 13 whose larger the user kept (0.98 and up). resdet names the smaller's size for 5 of the 9 (0.58–0.75), and for one image pair the user kept the larger of (logged twice, pairs 168 and 175: a rename, then a delete) at 0.56: a real upscale's source need not be the pair's smaller file (another reduction, another crop), and its confidence there sits near resdet's floor. A kept larger image can still be an upscale; the user is to look at that pair and at pair 163 (below) before a confidence bar is set.

**ird**, asked the same question (its log10 NFA at the distance a resampling from the smaller's size leaves, rank-transform preprocessing, `-5` its own bar), on a subset of the grid (factors 1.5, 2 and 3; genuine, nearest, bicubic, sharpened Lanczos; PNG and q90) and on the same Tumblr pairs: every upscale kept as PNG at the floor of −50, sharpened and nearest ones included; but a genuine larger copy sometimes too (−42 and −9 in two of the twelve), since a reduction of a larger original is itself resampled; and saved as JPEG q90, most 2× upscales are lost (the JPEG grid's distances are discarded). On the Tumblr pairs: 5 of the 9 upscales, and among the kept, pair 163 at −50 (its larger image, which `line_detail` puts at 1.40, sharper on its lines than the smaller: possibly a sharpened or AI upscale of a picture the size of the smaller). Where it misses at the smaller's size it can show another source: pair 1098's larger image (1454 × 1303) shows resampling from 952 × 853, against the smaller's 477 × 440 (twice that would be 954 × 880). About 5 s per image (`ird_check.py`). No better than resdet as a mark, with false hits on genuine reductions; useful as a research tool for how a file was made.

**AI upscalers** (`upscale_grid` alongside: each illustration's smaller copy, 384 px on its shorter side, blown up 2× and 4× by waifu2x's CUNet with and without denoising, Real-ESRGAN `x4plus-anime` and `animevideov3`, Real-CUGAN; as PNG and q90) escape all three tests:

| Larger copy | `line_detail` | resdet at the smaller's size |
|---|---|---|
| genuine | 0.90–1.00 | none |
| waifu2x CUNet | 0.86–1.00 | none |
| Real-ESRGAN `animevideov3` | 0.88–1.11 | at 4× only, 0.56–0.57 |
| Real-ESRGAN `x4plus-anime`, Real-CUGAN | 0.98–1.26 | none |

The sharper ones come out over 1, sharper on the lines than a genuine larger copy, but real larger copies the user kept reach 1.63 against a soft smaller one, so "too sharp" is no rule either. Telling AI upscales needs another method; none of the published ones has a tool for stills.

## How much a JPEG can be restored (T40)

`qs_gain.py`: each illustration reduced to 100, 50, 25 and 12 %, a central crop of at most 1024 px, saved by libjpeg-turbo at q20–95 in 4:2:0 and 4:4:4, then jpegQS (`-q 3` and `-q 6`, 3 iterations); SSIMULACRA2 and Butteraugli's 3-norm against the crop before JPEG (512 files).

* `-q 6` beats `-q 3` (median gain 3.6 SSIMULACRA2 points against 2.7). By SSIMULACRA2 it makes 6 of the 512 files worse, by Butteraugli 75: it smooths, and Butteraugli counts lost texture.
* The gain is largest at middle qualities and falls at the top: at full size about 4.5 points from q20 to q60, 2.4 at q75, 0.7 at q90, 0.1 at q95. Smaller copies keep more of it at high qualities (at 12 %: 3.3 at q85, 2.5 at q90).
* Read as the plain-JPEG quality the result is worth (the quality whose plain save scores as high), it depends on the file's quality alone, within a few points over size and subsampling:

| File's quality | 20 | 30 | 40 | 50 | 60 | 70 | 75 | 80 | 85 | 90 |
|---|---|---|---|---|---|---|---|---|---|---|
| with jpegQS -q 6, about | 22–23 | 33–35 | 46–50 | 58–64 | 67–72 | 76–78 | 80–82 | 85–86 | 88–90 | 91–93 |

**Two axes, not one** (the user's visual check, 2026-11-28, on q50 + jpegQS against plain q62 and q70, at full size and at 25 %): jpegQS removes most of the blocks, which makes it look far better than q62 and q70, but it does not bring back the thin lines and small detail strong compression blurs, which q70 keeps better (blush lines, thin hair ends on the 25 % copy). So a picture with little fine detail comes out much closer to its original than q70, one with much fine detail less so. `qs_gain.py --axes` measures the two separately: **fine detail**, the Laplacian's error on the original's strongest Laplacian pixels (its top 5 %, over the original's own there), and **blocks**, how much more the picture jumps across the 8 px block edges than inside the blocks, beyond the original's own; each restored file is then placed on each axis's plain-JPEG curve (512 files, the median over the four pictures and both subsamplings):

| File's quality | 30 | 50 | 70 | 85 | 90 |
|---|---|---|---|---|---|
| jpegQS -q 6: detail like, at 100 / 25 / 12 % | 45 / 36 / 39 | 57 / 56 / 61 | 72 / 74 / 74 | 86 / 86 / 86 | 90 / 91 / 90 |
| jpegQS -q 6: blocks like, at 100 / 25 / 12 % | 93 / 88 / 88 | 100 / 97 / 90 | 100 / 97 / 97 | 95 / 97 / 100 | 94 / 94 / 97 |
| jpeg2png: detail like, at 100 / 25 / 12 % | 44 / 28 / 28 | 63 / 45 / 44 | 76 / 64 / 64 | 86 / 79 / 80 | 89 / 84 / 84 |
| jpeg2png: blocks like, at 100 / 25 / 12 % | 100 / 90 / 86 | 100 / 91 / 86 | 100 / 92 / 87 | 100 / 94 / 89 | 100 / 96 / 89 |

So jpegQS's restoration is of the blocks: whatever the file's quality, they end up like a plain q88–100's, while the detail stays within a few points of the file's own quality (more at low qualities and small sizes). "Restorable to" is then two numbers, both read from the file's quality alone: the blocks of about a q90 or better, the detail of about the file's own quality.

**jpeg2png against jpegQS** (`qs_gain.py --axes --jpeg2png`, about 2 s per file): on the full-size illustrations jpeg2png is ahead on both axes and by SSIMULACRA2 (by 1.4 to 13 points on the four pictures at q30-85, 4:2:0), as its README says it is made for drawings; on the reduced copies it smooths the fine detail away, below even the plain JPEG's (q50 at 25 %: like a q45), where jpegQS keeps it (per-file figures, SSIMULACRA2 and Butteraugli included: the workspace's `Research\results\lower-quality\jpeg2png.txt`). Which restorer suits a file depends on its size and content; the user's visual check of the two side by side is pending.

These are a metric's readings; the user's eye has the last word.

Real files: of the 1,523 distinct JPEGs in the user's four real runs, 91 % carry libjpeg's standard tables at one quality, most at q90 (1,109) and q85 (177), where jpegQS adds about 2–3 quality points; 130 carry other tables.

## Other lossy formats (T40a)

No tool restores WebP, AVIF, HEIC or JPEG XL within the file's own quantisation, and there is little room for one: their decoders already filter block edges in the loop (JPEG XL even clamps its filter to the intervals), and a constrained restorer would have to re-create each codec's prediction and filtering around its coefficients. The learned restorers that work on any picture invent detail.

Palette images (GIF, PNG8) have a constraint of their own: each pixel's colour before quantising lay nearer its palette entry than any other. `palette_smooth.py` smooths a quantised crop (edge-preserving, OpenCV's bilateral filter) while keeping each pixel in its entry's cell: on two illustrations at 256, 64 and 16 colours it gains 0.1–1.7 SSIMULACRA2 points, against 0.0–0.9 for the same smoothing unconstrained; a dithered file has no per-pixel cell (its error went to the neighbours), and free smoothing gains it at most 0.6. A restorer built for it, as jpegQS is for JPEG, could do more; at these gains it is not worth a feature.

## A JPEG saved as a lossless file (T40b)

`jpeg_from_pixels.py` rebuilds the JPEG a lossless file was decoded from, so that jpegQS works on a PNG as on the JPEG: the decoder's own 8-bit planes recovered from the RGB, the block grid and the chroma's 16 px phase, the chroma layout and the IJG quality each tried by rebuilding a window, decoding it again exactly as libjpeg does and counting the pixels missed (its docstring has the details). `jpegcoef\` reads and writes a JPEG's coefficients, so the rebuilt file can be compared coefficient by coefficient. `jpeg_rebuild_check.py` checks it on the illustrations' JPEGs decoded by Pillow (libjpeg-turbo, fancy chroma upsampling) and by `djpeg -nosmooth` (chroma repeated), on the grid and 3 and 5 px off it.

Per quality, 32 files each: four pictures, 4:2:0 and 4:4:4, two decoders, on and off the grid. "Read right": the layout, the 16 px phase and both tables' quality; the share of non-zero coefficients rebuilt exactly, over the files read right; and SSIMULACRA2's gain over the PNG of jpegQS (`-q 3`) on the real JPEG and on the rebuilt one.

| Quality | Read right | Non-zero coefficients exact: luma, chroma (lowest, median) | jpegQS's gain: real JPEG, rebuilt |
|---|---|---|---|
| 30 | 30 of 32 | 94.4, 99.6 %; 99.6, 100 % | +3.76, +3.66 |
| 50 | 31 | 94.6, 99.7; 99.5, 100 | +3.46, +3.42 |
| 60 | 31 | 97.9, 99.6; 99.3, 100 | +4.01, +3.94 |
| 75 | 31 | 97.2, 99.5; 98.7, 99.9 | +2.91, +2.81 |
| 85 | 31 | 94.3, 97.4; 87.4, 92.5 | +2.23, +1.49 |
| 90 | 32 | 94.1, 96.6; 86.6, 90.2 | +1.45, +0.96 |
| 95 | 12 | 88.3, 90.1; 88.8, 90.7 | +0.35, +0.13 |

The six misreadings up to q85 were all one case, a 4:2:0 picture decoded with fancy upsampling and cut off the grid, whose own 16 px phase the chroma alone ranked below others; trying every layout in the joint check reads all six right (and the on-grid files as before, rechecked). What is not rebuilt exactly is mostly in blocks the decoder clipped at 0 or 255, which the check skips; at q85 and up, more coefficients are lost in the rounding, and jpegQS on the rebuilt file still gains, if less. A file not read is rebuilt with steps of 1: jpegQS then leaves it within 0.2 of the PNG, never far worse.

What it doesn't rebuild:

* Tables other than libjpeg's scaled standard ones (9 % of the real JPEGs above): it would need each step read on its own, which the rounding makes unreliable below a step of about 8 (a flat block's 64 pixels all round the same way, moving its DC by up to 4).
* Other decoders' IDCTs: libjpeg's fast integer IDCT misreads the quality. Windows' GDI+ gave the same pixels as Pillow on every test file. Photoshop's, ffmpeg's and browsers' other than libjpeg-turbo's were not tried.
* A picture changed after decoding, or decoded elsewhere. The real runs' saved pairs hold three distinct PNGs with a JPEG trace (`jpeg_history`): the Tumblr run's pair 154 (q75, 4:2:0) is rebuilt exactly; its pair 143 (trace about q60, off the grid by 6 and 5 px) converts as libjpeg's output does but fits no table short of q100's steps of 1, which fit anything, so it was most likely changed after decoding; the 2026-11 run's pair 1521 (trace q85) fits none either.
* WebP, AVIF and the others saved as PNG: their prediction and loop filters make the coefficients unrecoverable from pixels.

## What the PR could hold

Each is a property of one image, computed once and kept with its record, or of a pair, computed on the pair's overlap:

1. **A blown-up copy, marked.** On a pair of different sizes showing the same picture (the aligned search's transform gives the overlap): `line_detail` under its threshold, or resdet's question at the smaller's size above a confidence bar. The mark goes on the larger image.
2. **The JPEG quality, as the file has it and as the pixels show it.** The IJG quality of the file's table; for any file, the strongest JPEG save its pixels show (`jpeg_history`), so a PNG made from a q50 JPEG shows as such. `better_copy`'s effective quality is the lower of the two.
3. **Restorable to, on two axes.** For a JPEG, and for a lossless file that rebuilds into its JPEG: what jpegQS (or jpeg2png) leaves of each kind of loss (the table above). The blocks go, whatever the quality; the fine detail stays at about the file's own quality. So the file's quality still ranks copies by detail, and "restorable" says the blocks of the lower one need not count against it: a q50 JPEG of a picture with little fine detail is worth more than its number. How to show that in one place is the design's question.

Costs, as measured here: the file's table is read from its header; `jpeg_history` takes about 0.4 s per image on a 1536 px crop ([07](07-settings-study.md#which-copy-is-worse)); resdet about 0.9 s on a 1536 × 1018 picture, only for the larger image of a pair of different sizes; `line_detail` works on the pair's overlap at the smaller's size. Rebuilding a JPEG from a PNG takes 10-20 s per picture in Python, nearly all of it trying 100 qualities in 9 chroma layouts on one window, and is needed only for a lossless file with a JPEG trace.

## Tools

`qs_gain.py` (with `--axes`, `--jpeg2png`), `upscale_grid.py` (with `--ai`), `upscale_check.py --resdet`, `ird_check.py`, `jpeg_rebuild_check.py`, `jpeg_from_pixels.py`, `jpegcoef\` and `palette_smooth.py`; see [tools/README.md](tools/README.md).
