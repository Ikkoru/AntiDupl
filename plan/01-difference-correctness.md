# 01 — Making the `Difference` column correct

Covers the user's issues 2–4 ("Difference makes mistakes", "pixel-identical pairs missing at 0 %", "0.00 that isn't identical"). All numbers below were reproduced with [`tools/`](tools/README.md).

## How AntiDupl computes `Difference` today (SSIM mode)

1. **Decode.** [`TImage::Load`](../src/AntiDupl/adImage.cpp) picks the decoder by sniffing bytes: `TTurboJpeg::Supported()` only returns true when the file starts with `FF D8 FF E0` ([adTurboJpeg.cpp:101](../src/AntiDupl/adTurboJpeg.cpp#L101)), i.e. a JFIF APP0 segment. Every other JPEG (EXIF-first `FFE1`, Photoshop `FFED`, ICC `FFE2`, bare `FFDB`, …) goes to GDI+.
2. **Gray + reduce.** [`TDataCollector::FillPixelData`](../src/AntiDupl/adDataCollector.cpp#L70) converts the view to gray (`BgraToGray` for anything labelled `Bgra32`), bilinear-resizes it to 256×256 (`Simd::Resize` default = bilinear, line 101), then `ReduceGray2x2` to 128×128. The 128×128 plane (+ float `average`/`varianceSquare`) is cached in the image database (`…\user\images\128x128\*.adi`).
3. **Compare.** [`TImageComparer_SSIM::IsDuplPair`](../src/AntiDupl/adImageComparer.cpp#L332) computes a single-window (global) SSIM of the two 128×128 planes in `float`, `difference = 100·(1 − SSIM)`, rejects the pair if `difference > thresholdDifference` (integer %), and finally adds `ADDITIONAL_DIFFERENCE_FOR_DIFFERENT_CRC32 = 1e-6` when the files' CRC32C differ (line 416).
4. **Display.** [ResultRowSetter.cs:325-329](../src/AntiDupl.NET.WinForms/ResultRowSetter.cs#L325): `ToString("F2")`; bold + `LightGreen` only when `difference == 0` exactly.

## Bug A — TurboJPEG path swaps red and blue (root cause of "Identical but 0.22 / 0.08")

[adTurboJpeg.cpp:58-59](../src/AntiDupl/adTurboJpeg.cpp#L58):

```cpp
TView * pView = new TView(width, height, TView::Bgra32, NULL, 4);
if (::tjDecompress2(_handle, data, size, pView->data, width, 0, height, ::TJPF_RGBA, flags) != 0 ...
```

`TJPF_RGBA` writes bytes R,G,B,A into a view labelled `Bgra32`, so `BgraToGray` uses `0.114·R + 0.587·G + 0.299·B` instead of `0.299·R + 0.587·G + 0.114·B`. Present since the TurboJPEG path was added in 2019 (`d3260a7`).

**Evidence.** Both "Identical" pairs are lossless transcodes (same DQT, one progressive + `FFED` first, one baseline + JFIF first); decoded pixels are bit-identical. File (1) goes to GDI+ (correct gray), file (2) to TurboJPEG (swapped gray). Re-running AntiDupl's exact arithmetic:

| Pair | Decoders now | Current build | Shown | After fix |
|---|---|---|---|---|
| Identical but 0.22 | GDI+ / TurboJPEG | 0.217453 | **0.22** | 0 |
| Identical but 0.08 | GDI+ / TurboJPEG | 0.076530 | **0.08** | 0 |
| Different but 0.00 | TurboJPEG / TurboJPEG | 0.000496 | **0.00** | 0.000253 |

The error is bigger for the bluer image (0.22) than the greyer one (0.08), as expected from an R↔B swap.

**Same bug, other symptoms (upstream):** everything that displays through the core loader (`adLoadBitmapW` → `Simd::Resize` of the mislabelled view, [adImageUtils.cpp:78](../src/AntiDupl/adImageUtils.cpp#L78)) shows JFIF JPEGs with red/blue swapped — the big preview for paths ≥ 260 chars ([PictureBoxPanel.cs:122](../src/AntiDupl.NET.WinForms/GUIControl/PictureBoxPanel.cs#L122) only uses GDI+ for short paths) and the grouped-thumbnails view (`ThumbnailStorage`; its menu entry is currently commented out in `ViewModeMenuItem.cs`): [ermig1979/AntiDupl#122](https://github.com/ermig1979/AntiDupl/issues/122) ("reddish tint"), [ermig1979/AntiDupl#236](https://github.com/ermig1979/AntiDupl/issues/236) ("long path names cause colour distortion"). The user never sees it because the pair preview uses .NET/GDI+ for normal paths. Also affects blockiness/blurring values of JFIF JPEGs (computed from the same gray image).

**Fix (1 line):** `::TJPF_RGBA` → `::TJPF_BGRA`. Must ship together with Bug C (cache invalidation).

## Bug B — decoder chosen by the 4th byte of the file

Even with Bug A fixed, a pixel-identical pair can still be decoded by two different libraries (libjpeg-turbo vs GDI+'s IJG-derived codec), which is the wrong kind of variability for a duplicate finder, and TurboJPEG failures have **no fallback** ([adImage.cpp:112-118](../src/AntiDupl/adImage.cpp#L112) returns whatever `TTurboJpeg::Load` returns, including `NULL`).

**Fix:**

```cpp
// adTurboJpeg.cpp — any JPEG: SOI followed by a marker
bool supported = (size >= 3 && data[0] == 0xFF && data[1] == 0xD8 && data[2] == 0xFF);

// adImage.cpp — replace the #ifdef block + dangling else
#ifdef AD_TURBO_JPEG_ENABLE
        if (pOptions->advanced.useLibJpegTurbo && TTurboJpeg::Supported(hGlobal))
        {
            if (TImage* pImage = TTurboJpeg::Load(hGlobal))   // CMYK/corrupt/unsupported -> NULL
                return pImage;
        }
#endif
        return TGdiplus::Load(hGlobal);
```

**Watch out — EXIF.** Only the GDI+ path fills `TImage::m_exifInfo` ([adGdiplus.cpp:254](../src/AntiDupl/adGdiplus.cpp#L254)); TurboJPEG/WebP/AVIF/JXL/HEIF never do. Routing all JPEGs to TurboJPEG would silently blank the EXIF fields the UI shows for JPEGs. Add `bool TGdiplus::LoadExif(HGLOBAL, TImageExif*)` (factor `GetExifProperty` out; GDI+ parses metadata without decoding pixels until `LockBits`/`DrawImage`) and call it from `TTurboJpeg::Load`. Measure the cost; if noticeable, parse APP1 directly (only 7 tags are used: ImageDescription, Make, Model, Software, DateTime, Artist, UserComment).

## Bug C — stale image database after A/B

The `.adi` cache stores the 128×128 planes keyed by path + size + mtime. After A/B, cached planes of every JFIF JPEG are wrong (swapped) while newly computed ones are right — mixing them is worse than either. "Delete irrelevant records from a database of image" only drops records of missing files, so it doesn't help.

**Fix:** bump `FILE_VERSION` 4 → 5 ([adConfig.h:107](../src/AntiDupl/adConfig.h#L107)) and, in `TInputFileStream::Load(TImageData&)` ([adFileStream.cpp:154](../src/AntiDupl/adFileStream.cpp#L154)), when `m_version < 5` read the old record but then set `data->filled = false`, `blockiness = -1`, `blurring = -1` so `PixelDataFillingNeed()` ([adImageData.cpp:112](../src/AntiDupl/adImageData.cpp#L112)) recomputes it. Keep type/size/crc/defect. Note: `.adr` (results) and `.adm` (mistakes) share the version header; files written by the new build can't be read by old builds (fine; document it). Bundle every per-image format change planned in this folder (sums, pixel hash, colour thumbnail, area resampling) into this one bump for the local build so the user re-decodes the library only once.

## Bug D — float noise: identical planes get 7.6e-6 (≈30 % of the time)

[adImageComparer.cpp:355-416](../src/AntiDupl/adImageComparer.cpp#L355): mean/variance are cached as `float`, the formula mixes `float` and `double` (`pow(float, 2)` resolves to the `double` overload under `<cmath>`), and the C++ project is compiled with `/fp:fast` ([Prop.props:39](../src/Prop.props#L39)), so for identical planes `res` can land on 1 − 6e-8 → `difference = 7.63e-6` (or 1.53e-5). A Python model of this arithmetic hits it about a third of the time; MSVC's exact rate may differ, the effect is the same. Consequences, all observed by the user or upstream:

* shows "0.00" but **not** bold green (needs `== 0`) — [ermig1979/AntiDupl#186](https://github.com/ermig1979/AntiDupl/issues/186) "Not all duplicates being flagged as identical" (hard-linked files!),
* **dropped when Threshold difference = 0 %** (`difference > 0`) — user's issue 3,
* hint logic's `difference == 0` branch ([adHintSetter.cpp:77](../src/AntiDupl/adHintSetter.cpp#L77)) skipped.

`tools/float_noise.py`: 905 of 3000 identical self-comparisons (30.2 %) → non-zero.

**Fix:**

1. Store exact integer moments in `TPixelData` instead of floats: `TUInt64 sum, sumSquare` computed once in `FillPixelData` (`SimdValueSum`/`SimdSquareSum`); persist them (FILE_VERSION 5). This also removes the `average == 0` "not computed yet" sentinel and the unsynchronised writes to shared `TPixelData` from multiple compare threads (`IsDuplPair` currently mutates both images and calls `SetSaveState`).
2. In `IsDuplPair`, after the type/size/ratio/folder filters:
   ```cpp
   const size_t n = pFirst->data->size;                    // side*side
   double difference;
   if (memcmp(pFirst->data->main, pSecond->data->main, n) == 0)
       difference = 0.0;                                   // identical planes: exact, no float noise
   else
   {
       uint64_t corr = 0;
       SimdCorrelationSum(a, side, b, side, side, side, &corr);
       const double N = double(n);
       const double m1 = pFirst->data->sum / N, m2 = pSecond->data->sum / N;
       const double v1 = pFirst->data->sumSquare / N - m1 * m1, v2 = pSecond->data->sumSquare / N - m2 * m2;
       const double cov = corr / N - m1 * m2;
       const double C1 = Square(0.01 * 255.0), C2 = Square(0.03 * 255.0);
       const double ssim = (2 * m1 * m2 + C1) * (2 * cov + C2) / ((m1 * m1 + m2 * m2 + C1) * (v1 + v2 + C2));
       difference = std::max(0.0, 100.0 * (1.0 - ssim));
   }
   ```
3. Switch `FloatingPointModel` to `Precise` in [Prop.props](../src/Prop.props#L39) (only the C++ project imports it; Simd comes pre-built from vcpkg, so hot loops are unaffected). At minimum wrap the comparer in `#pragma float_control(precise, on, push)`.
4. The squared-sum comparers are integer-exact already (`sqrt(mainDifference/…)` is 0 for identical planes).

## Feature E — "0 means pixel-identical" (and nothing else)

Even with A–D, (a) two *different* images can share a 128×128 plane (differences vanish at thumbnail scale → exact 0), and (b) a pixel-identical but byte-different pair (the user's "Identical" pairs: lossless transcodes / metadata-only edits) ends at 1e-6 because of the CRC epsilon. The user wants 0 to mean pixel-identical.

**Design (no ABI/file-format change for results):**

* New per-image `TUInt64 pixelHash` in `TImageData`, computed in `FillPixelData` from the full-resolution decoded view normalised to BGRA rows (`width*4` bytes per row, stride padding skipped; JXL `Rgba32` and HEIF `Rgb24` converted first) plus width/height. Use `XXH3_64bits` (vcpkg port `xxhash` 0.8.3 exists at the pinned baseline; add `"xxhash"` to [vcpkg.json](../src/vcpkg.json)). Persist it (FILE_VERSION 5). `TImageData::Turn()`/`Mirror()` set `pixelHash = 0` so rotated/mirrored copies never count as identical.
* In every `IsDuplPair` (SSIM, squared-sum, and the new modes of [02](02-comparison-modes.md)), after the filters:
  ```cpp
  const bool samePixels = pFirst->pixelHash && pFirst->pixelHash == pSecond->pixelHash &&
                          pFirst->width == pSecond->width && pFirst->height == pSecond->height;
  double difference = samePixels ? 0.0 : std::max(Metric(...), MIN_NONIDENTICAL_DIFFERENCE); // 1e-4
  if (difference > m_pOptions->compare.thresholdDifference) return false;
  *pDifference = difference;
  if (pFirst->crc32c != pSecond->crc32c)
      *pDifference += ADDITIONAL_DIFFERENCE_FOR_DIFFERENT_CRC32;                             // 1e-6
  ```
  Resulting encoding of `difference`, consistent with today's hint logic:

  | Value | Meaning |
  |---|---|
  | `0` | byte-identical files (same CRC32C) |
  | `1e-6` | pixel-identical, different bytes (metadata, progressive/baseline, …) |
  | `≥ 1e-4` | pixels differ (metric value, floored) |

* Threshold 0 % now means exactly "pixel-identical" (both identical classes pass, nothing else does).
* Sorting ascending puts byte-identical, then pixel-identical, then everything else — no UI work needed.
* (Later, optional) replace the epsilon trick with explicit `identity` flags in `adResult` (ABI change).

## Feature F — display rule chosen by the user

> "As long as it sorts correctly, the column remains narrow, and I don't get confused by a 0.00 that has changes … Can it just show 0.01 on any (0; 0.01]?"

One helper used by [ResultRowSetter.cs:325](../src/AntiDupl.NET.WinForms/ResultRowSetter.cs#L325) and [ClipboardContentBuilder.cs:77](../src/AntiDupl.NET.WinForms/ClipboardContentBuilder.cs#L77):

```csharp
public static string FormatDifference(double d) =>
    d < 1e-5  ? "0.00"                 // byte- or pixel-identical (0 or the 1e-6 CRC epsilon)
  : d <= 0.01 ? "0.01"                 // any real difference is never shown as 0.00
  : d.ToString("F2");
```

Styling: `d == 0` → bold + "identical" colour; `0 < d < 1e-5` → regular + same colour, tooltip "Pixel-identical (file bytes differ)"; tooltip on every cell with `d.ToString("R")`. Colours come from the theme helper of [04](04-dark-mode.md) (today's `LightGreen` is barely readable on white). Sorting is done in the core on the raw double ([adResult.cpp:238-241](../src/AntiDupl/adResult.cpp#L238)), so it stays exact.

## Optional G — area resampling for the 128×128 plane

`Simd::Resize(gray, 256×256)` defaults to bilinear, which at 4000→256 samples ~2 of every 15 pixels (aliasing). Measured on a 3500×2800 illustration, current metric, same decoder:

| Copy | Bilinear (today) | Area (`SimdResizeMethodArea`) |
|---|---|---|
| JPEG q95 / q60 / q40 | 0.0020 / 0.0299 / 0.0453 | 0.0007 / 0.0029 / 0.0043 |
| downscaled 50 % | 0.1164 | 0.0023 |
| colour variant, same luma | 0.0058 | 0.0056 |
| local recolour 5 % | 0.0362 | 0.0378 |

Area resampling makes re-saves/resizes 3–50× "closer" without hiding edits (it does not fix the colour-blindness — see [02](02-comparison-modes.md)). One-line change at [adDataCollector.cpp:101](../src/AntiDupl/adDataCollector.cpp#L101) (`Simd::Resize(gray, *m_pGrayBuffers.front(), SimdResizeMethodArea)`, or resize straight to `reducedImageSize`). It shifts every SSIM value, so upstream it should be an option; in the local build just do it inside the FILE_VERSION 5 bump.

## Test plan

1. `tools/repro_difference.py` on the three example pairs → expected values above; then run the real build on a folder with the six example files: both "Identical" pairs show `0.00` (green, not bold), "Different" shows `0.01`, and all four identical-class files remain at threshold 0 %.
2. Copy a JPEG to a second folder and hard-link another → `0.00` **bold**, at 0 % threshold, every time (repeat 20×: the 30 % float noise must be gone).
3. Re-save a JPEG losslessly with `jpegtran -progressive` and with `exiftool -all=` → pixel-identical class.
4. A JFIF JPEG under a path longer than 260 characters: preview colours correct (#236).
5. Start with an old `images\128x128` DB → everything recomputed once, no mixed values.
6. A CMYK JPEG and a truncated JPEG still load (GDI+ fallback). EXIF column still filled for EXIF JPEGs.
