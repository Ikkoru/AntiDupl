# 06 — Stretch goals (noted, not researched) and other improvements

Numbering follows `tasks.md`; S1 (metadata merge) has its own document, [05](05-metadata-merge.md).

## S2 — Built-in QuantSmooth pass before comparing JPEGs *(user's spec — not started)*

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

## S3 — Comparison-engine research *(done — see [02-comparison-modes.md](02-comparison-modes.md))*

## S4 — Other improvements found while reading the code

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
| A11 | Compile with `/utf-8`: the C++ sources are UTF-8, most without BOM, so MSVC reads them in the ANSI code page (warning C4819). On a CJK-locale PC a comment ending in Cyrillic/CJK text then swallows its line end — harmless with a CRLF checkout, but with LF line ends the next line of code joins the comment | [Prop.props](../src/Prop.props) `AdditionalOptions` | upstreamable; the user's PC (cp932) builds with `CL=/utf-8` meanwhile |
| A12 | vcpkg libraries built with MSVC 14.51 (v145): libde265 1.0.16's `de265_init()` runs off the start of a scan table in `init_scan_orders()`; libheif calls it from a static constructor, so `AntiDupl.dll` fails to load (error 1114) and the program closes silently. The same source and flags built with MSVC 14.44 (v143) work; `scan.cc` compiled on its own works with both, so the trigger lies elsewhere in the library | [AntiDupl_CI.yml](../.github/workflows/AntiDupl_CI.yml), vcpkg triplet | upstream's CI breaks once `windows-latest` builds with Visual Studio 2026; pin `VCPKG_PLATFORM_TOOLSET v143`, and report it (Microsoft / libde265) with a minimal repro |

## S5 — Mistakes list

How it works today:

* An entry identifies a file by **path + file size + modification time** ([adImageInfo.cpp:117](../src/AntiDupl/adImageInfo.cpp#L117), lookups in [adMistakeStorage.cpp](../src/AntiDupl/adMistakeStorage.cpp)); the stored "hash" is a CRC of the path, not of the content. A rename done inside AntiDupl carries the entries along (`TMistakeStorage::Rename`, line 177); moving, renaming or editing a file anywhere else (retagging changes size and date) makes its entries stop matching.
* *Remember mistakes* (Options → Advanced, `mistakeDataBase`) only decides whether a **search** drops pairs found in the list ([adResultStorage.cpp:91](../src/AntiDupl/adResultStorage.cpp#L91), 121). Marking a pair as a mistake records it either way ([adUndoRedoEngine.cpp:416-423](../src/AntiDupl/adUndoRedoEngine.cpp#L416)). Switching it doesn't refilter the current results.
* *Search → Check the database of mistakes at loading* (`checkMistakesAtLoading`) discards, at start-up, every entry whose file is missing or changed ([adMistakeStorage.cpp:88, 99](../src/AntiDupl/adMistakeStorage.cpp#L88)); the list is saved without them on exit, so they are gone for good. Starting AntiDupl while a drive (the user's `Z:`) is offline wipes every entry on it.

Stretch items:

* **Verify** *Remember mistakes* as a search filter (the user remembers it not working once): off → a new search shows marked pairs; on → it hides them; check whether it ever needs a new search or a restart.
* **Clearer labels:** *Remember mistakes* → e.g. "Hide pairs marked as mistakes in searches"; *Check the database of mistakes at loading* → e.g. "At start-up, forget mistakes whose files moved or changed".
* **Quick toggle** for that filter in the Search menu / toolbar.
* **Offline-drive guard:** the start-up check skips entries on a drive or share that isn't available instead of discarding them.
* **Path-independent matching:** identify files by content — the pixel hash of T8, or a file hash — so moving, renaming or retagging keeps the mistakes; fill the hash for existing entries the first time their files are seen.
