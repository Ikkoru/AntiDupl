# 06 — Stretch goals (noted, not researched) and other improvements

## S1 — Built-in QuantSmooth pass before comparing JPEGs *(user's spec — not started)*

User's requirements, verbatim in substance:

* Run a QuantSmooth (QS) pass on JPEGs **before comparison**, writing the QS outputs to a **temporary folder**.
* All image operations (delete / replace / rename / move) still act on the **originals**.
* All details shown (size, type, dates, EXIF, path …) are those of the **originals**.
* When a decision is made about a pair (delete/replace 1 or 2, or keep both = "mistake"), the temporary QS versions of **those** images are deleted.
* QS images that are **not currently open in the program** and **older than a week** are deleted.

Pointers for whoever picks this up (from reading the code, not researched further):

* Comparison input comes from `TDataCollector::FillPixelData` ([adDataCollector.cpp:70](../src/AntiDupl/adDataCollector.cpp#L70)); feeding it the QS output keeps everything else (paths, sizes, CRC, EXIF) on the original. Keep pixel identity ([01 § E](01-difference-correctness.md)) on the **original** pixels.
* Cache: the image DB stores reduced data per path+size+mtime; QS-derived data needs its own cache directory (e.g. `images\128x128_qs`) or a flag in the record, otherwise toggling QS mixes data.
* Preview / Ctrl+D external diff: decide whether they show QS or original (user's current "QS Compare" script suggests QS for the diff tool).
* Decision hooks: the action dispatch in `ResultsListView.MakeAction` / `ProgressForm` (delete, rename, mistake); age-based cleanup at start-up and after each search.
* The user's existing tool: `…\hidpi-manga\tools\sendto\QS Compare (no menu).cmd`.

## S2 — Comparison-engine research *(done — see [02-comparison-modes.md](02-comparison-modes.md))*

## S3 — Other improvements found while reading the code

| # | Item | Where | Why |
|---|---|---|---|
| A1 | HEIF images with alpha are decoded as RGBA but labelled `Rgb24` → garbage gray plane/thumbnails | [adHeif.cpp:92,105](../src/AntiDupl/adHeif.cpp#L92) | label `Rgba32` when `img_has_alpha` |
| A2 | "JPEG quality" column (estimated from DQT tables, like ImageMagick `%Q`) and "bits per pixel" column | core `TImageInfo` + UI columns | directly answers "which one is the worse compression"; could feed the auto-hint |
| A3 | Hint policy for pixel-identical pairs (keep smaller file? file with more metadata?) | [adHintSetter.cpp:77](../src/AntiDupl/adHintSetter.cpp#L77) | user doesn't use hints today; make it an option if they start |
| A4 | EXIF orientation is ignored by every decoder | decoders | rotated copies only match with "transformed image" on |
| A5 | Crop-tolerant matching: align thumbnails (scale/offset search) before the local metrics | [02](02-comparison-modes.md) | every metric tested calls a 1 % border crop "very different" |
| A6 | Highlight-differences feature: `ComparableBitmap` reads only one channel of a GDI+-grayscaled copy, `Comparator.Distance` truncates with integer division | [ComparableBitmap.cs](../src/AntiDupl.NET.WinForms/ComparableBitmap.cs), [Comparator.cs](../src/AntiDupl.NET.WinForms/Comparator.cs) | colour-only edits never highlighted; could reuse the colour block metric |
| A7 | `Options.Load()` silently resets everything on any error | [Options.cs:106](../src/AntiDupl.NET.WinForms/Options.cs#L106) | covered in [03](03-ui-bugs.md) |
| A8 | Explicit identity flags in `adResult` instead of the `1e-6` CRC epsilon | `AntiDupl.h` `adResult`, `CoreDll.cs` | cleaner than encoding state in a float (ABI change) |
| A9 | `/fp:fast` for the whole core | [Prop.props:39](../src/Prop.props#L39) | covered in [01](01-difference-correctness.md) |
| A10 | Tooltip on the Difference cell with the full-precision value | ResultRowSetter | sorting is exact, display isn't |
