# Tasks — AntiDupl local build

Evidence and designs: [`plan/README.md`](plan/README.md) (read first). Every task links to its section. Priorities: **P0** proven bugs (upstream-worthy), **P1** requested features, **P2** stretch goals. Each P0/P1 item should be its own commit (and, where marked ⬆, its own upstream PR branch off `upstream/master`).

## P0 — Bugs (root causes proven)

- [ ] **T0 ⬆ Build fails from folders with spaces/commas** (the user's case). Quote the paths in the C# build events (`AntiDupl.NET.WinForms.csproj:43` → `CopyData.cmd`, `AntiDupl.NET.Core.csproj:75` → `External.cmd`) and make both scripts use `%~1`/`%~2` with quoted expansions. Done when a clean x64 Release build succeeds under `…\Coding, etc\Claude Code\Anti-Dupl\AntiDupl.NET`.
- [ ] **T1 ⬆ TurboJPEG decodes red/blue swapped.** `TJPF_RGBA` → `TJPF_BGRA` in `src/AntiDupl/adTurboJpeg.cpp:59`. Done when: `plan/tools/repro_difference.py` cases behave as listed and the real build shows `0.00` for both "Identical" example pairs; previews of JFIF JPEGs under >260-char paths show correct colours (upstream #122, #236). → [01 § A](plan/01-difference-correctness.md)
- [ ] **T2 ⬆ JPEG decoder chosen by the 4th byte.** `TTurboJpeg::Supported` accepts any `FF D8 FF`; GDI+ fallback when TurboJPEG fails; keep EXIF for JPEGs (`TGdiplus::LoadExif`). → [01 § B](plan/01-difference-correctness.md)
- [ ] **T3 ⬆ Stale image database.** `FILE_VERSION` 4 → 5, discard pixel data/blockiness/blurring of older records. Bundle every per-image format change (T4, T8, T10) into this one bump for the local build. → [01 § C](plan/01-difference-correctness.md)
- [ ] **T4 ⬆ Float noise in SSIM** (identical planes → 7.6e-6 in ~30 % of cases; not green, dropped at 0 %; upstream #186). Exact `sum`/`sumSquare`, double math, `memcmp` shortcut, `/fp:precise`. → [01 § D](plan/01-difference-correctness.md)
- [ ] **T5 ⬆ View mode resets / stacked two-value cells.** Options → Cancel replaces `resultsOptions` (`CoreOptionsForm.cs:879`); full `ResultsOptions` copy ctor; restore-in-place on Cancel/✕; row setter uses the grid's actual mode; `Options.Load` keeps a `.bad` copy instead of silently resetting (upstream #242). → [03 § H](plan/03-ui-bugs.md)
- [ ] **T6 ⬆ Janky sorting.** No left/right swap for non-`BySorted*` types (and only strict swaps for them); total-order tie-breaks + `stable_sort`; natural (`StrCmpLogicalW`) order for display sorts (upstream #241). → [03 § I](plan/03-ui-bugs.md)

## P1 — Requested features

- [ ] **T7 ⬆ Dark mode** (Windows 11): *View → Theme* (System/Light/Dark), `Application.SetColorMode` before any UI, `ThemeColors` helper, grid headers, verification list. → [04](plan/04-dark-mode.md)
- [ ] **T8 ⬆ "0 means pixel-identical".** XXH3-64 hash of the full decoded pixels; `0` = byte-identical, `1e-6` = pixel-identical, `≥ 1e-4` = different; threshold 0 % = pixel-identical only. → [01 § E](plan/01-difference-correctness.md)
- [ ] **T9 ⬆ Difference display rule** (user's choice): `0.00` only when identical, any value in (0; 0.01] shows `0.01`, else 2 decimals; bold = byte-identical, tooltip with the exact value; same in clipboard copy. → [01 § F](plan/01-difference-correctness.md)
- [ ] **T10 Cache everything every mode needs, once.** 64×64 colour thumbnail (area-resampled), area resampling for the 128×128 gray plane. → [01 § G](plan/01-difference-correctness.md), [02](plan/02-comparison-modes.md)
- [ ] **T11 Algorithm "Local colour difference"** (fast; worst 4×4 block of 64×64 colour thumbnails; default threshold 4). → [02](plan/02-comparison-modes.md)
- [ ] **T12 Algorithm "Perceptual (Butteraugli)"** (vendored google/butteraugli; candidates from the cheap metric; working size option 384/512/768/1024, default 512; per-pair score cache). → [02](plan/02-comparison-modes.md)
- [ ] **T13 (optional)** Store all cheap metrics per result and show them as sortable columns, so switching what you sort by needs no new search. → [02](plan/02-comparison-modes.md)
- [ ] **T14 Calibrate** default thresholds on the user's real duplicate/variant sets (`plan/tools/metric_experiment.py`). → [02](plan/02-comparison-modes.md)

## P2 — Stretch goals (noted; not to be done unless asked)

- [ ] **S1 "Delete but add metadata to other image".** Copy missing tags (incl. AI-generator prompts, settings, ComfyUI workflows) from the deleted file into the kept one with ExifTool; undo keeps working. Design and verified ExifTool commands → [05](plan/05-metadata-merge.md)
- [ ] **S2 Built-in QuantSmooth pass** — user's specification, verbatim:
      > Built-in QuantSmooth pass before comparison of jpgs creating a temporary folder of QS outputs. All image operations should still affect the originals. All details/info should be that of the originals. When a decision is made about an image pair (delete/replace 1/2 or keep both) the temporary versions of those images should be deleted. QSed images that are not currently open in the program, and are more than a week old should be deleted.

      Code pointers only (not researched) → [06 § S2](plan/06-stretch-and-ameliorations.md)
- [x] **S3 Research better comparison engines for my purposes** — done: Butteraugli best, cheap colour block metric second; hashes/DSSIM/SSIM variants unsuitable; size study. → [02](plan/02-comparison-modes.md)
- [ ] **S4 Other ameliorations** found while reading the code (HEIF-with-alpha bug, JPEG-quality and bits-per-pixel columns, hint policy for identical pairs, EXIF orientation, crop-tolerant alignment, colour-aware difference highlighting, explicit identity flags, tooltip) → [06 § S4](plan/06-stretch-and-ameliorations.md)

## Notes for the implementing session

* Code in the plan is a sketch written without a compiler (the C++ core builds only on Windows/MSVC) — verify each change in the app.
* There are no automated tests; each plan document ends with a manual test list.
* Image DB: `<user folder>\images\128x128\` (release: `%LOCALAPPDATA%\AntiDupl.NET\user`, dev builds: the `-s` folder) — expect a one-time full re-scan after T3.
