# AntiDupl local build — research results and implementation plan

Hand-off for a local Claude Code session (Windows 11, Visual Studio + vcpkg) working on the fork
`Ikkoru/AntiDupl` (base: upstream `ermig1979/AntiDupl` `e06d082`, v2.3.13). The checklist is in
[`../tasks.md`](../tasks.md); this folder holds the evidence and the designs.

## The user's setup (from `options.xml` / `default.xml`)

*Table of horizontal pairs*, algorithm **SSIM**, threshold **1 %**, sorted by **Difference ascending**,
reduced image size 128, *use database of image* on, *use libjpeg-turbo* on, compare inside one search path,
3 artist folders per scan. Hot keys: NumPad1/NumPad2 delete first/second, NumPad5 mistake, Ctrl+D external
diff ("QS Compare" script). Goal: delete the worse-compressed copy, keep similar-but-distinct images.

## Decisions taken with the user

| Question | Answer |
|---|---|
| Windows version (dark mode API is official on Win 11) | **Windows 11** → .NET 10 built-in dark mode |
| How far to take metric improvements | **Add them as more "Algorithm" choices** next to Mean square / SSIM; switching modes must not redo costly work |
| Delete-but-keep-metadata: what to carry over | **Missing tags only, including AI-generator data** (prompts, settings, workflows) |
| Difference display | Sort correctly, keep the column narrow, never show `0.00` for a changed image: **`0.00` only for identical, anything in (0; 0.01] shows `0.01`**, otherwise 2 decimals |
| Speed | Slower (even "decently") comparisons are fine |

## Findings at a glance

| # | User-visible problem | Root cause (proven) | Plan | Upstream |
|---|---|---|---|---|
| 1 | Pixel-identical pairs show 0.22 / 0.08 | TurboJPEG decodes R/B swapped (`TJPF_RGBA` into a `Bgra32` view) **and** only files starting `FF D8 FF E0` use TurboJPEG, the rest GDI+ → same pixels, different gray | [01 § A–C](01-difference-correctness.md) | fixes [#122](https://github.com/ermig1979/AntiDupl/issues/122), [#236](https://github.com/ermig1979/AntiDupl/issues/236) |
| 2 | Identical images missing at threshold 0 %, not green | float32/`/fp:fast` SSIM gives 7.6e-6 for identical planes ~30 % of the time | [01 § D](01-difference-correctness.md) | fixes [#186](https://github.com/ermig1979/AntiDupl/issues/186) |
| 3 | `0.00` shown for images that differ | 2-decimal rounding + tiny real differences; no pixel-identity concept | [01 § E–F](01-difference-correctness.md) | — |
| 4 | Variants vs worse copies not separated | one global grayscale SSIM on 128 px; colour-blind, insensitive to local edits | [02](02-comparison-modes.md) | — |
| 5 | Horizontal/vertical mode resets; stacked two-value cells | Options → **Cancel** replaces `resultsOptions` with a clone that lacks the view mode and all event subscribers | [03 § H](03-ui-bugs.md) | — |
| 6 | Janky sorting, history-dependent | every pair left/right-swapped on most sorts; unstable `std::sort` without tie-breakers; no natural order | [03 § I](03-ui-bugs.md) | — |
| 7 | No dark mode | — | [04](04-dark-mode.md) | [#115](https://github.com/ermig1979/AntiDupl/issues/115) |
| 8 | (stretch) keep metadata of the deleted copy | — | [05](05-metadata-merge.md) | — |
| 9 | (stretch) QuantSmooth pre-pass, other improvements | — | [06](06-stretch-and-ameliorations.md) | — |

Reproduction (any OS with Python): `tools/repro_difference.py` prints 0.217453 / 0.076530 / 0.000496 for the
three example pairs — AntiDupl shows 0.22 / 0.08 / 0.00 — and 0 / 0 / 0.000253 after the fixes.

## Workarounds with the current release

1. **Identical-but-0.22:** Options → Advanced → untick *Use libjpeg-turbo* (every JPEG then goes through
   GDI+, no swap), close AntiDupl, delete `%LOCALAPPDATA%\AntiDupl.NET\user\images\128x128\` (stale cached
   planes; the "Delete irrelevant records" menu does not remove them), restart, search again. Expected: the
   example pairs show 0.00 — never green (green currently requires byte-identical files) and still
   occasionally missing at threshold 0 % (bug 2). Not verified on Windows from here, but both files then
   use the same decoder.
2. **View mode:** use **OK**, never Cancel/✕, in the Options dialog; after a Cancel re-select
   *View → Table of horizontal pairs*.

## Order of work and upstream PRs

Small, independent PRs against `ermig1979/AntiDupl:master` (active maintainer: Edi61; CI = GitHub Actions
`windows-latest` MSBuild), then merge them all into the local-build branch:

1. `fix(turbojpeg)`: `TJPF_BGRA` + FILE_VERSION bump/stale-pixel invalidation (#122, #236).
2. `fix(jpeg)`: every JPEG through TurboJPEG when enabled, GDI+ fallback, EXIF still read.
3. `fix(ssim)`: exact moments, double math, identical-plane shortcut, `/fp:precise` (#186).
4. `fix(ui)`: Options Cancel no longer replaces `ResultsOptions`; full copy ctor.
5. `fix(sort)`: no pair swapping for non-"sorted" types, total-order tie-breaks, natural order.
6. `feat(ui)`: dark mode option (#115).
7. `feat`: pixel identity + difference display rule.
8. `feat`: Local colour / Butteraugli algorithms (open an issue first — bigger design change).
9. Local-only unless upstream wants them: area resampling, metadata merge, QuantSmooth.

## Build & verify

Visual Studio with the v143 toolset, ".NET desktop" + "Desktop C++" workloads, .NET 10 SDK, vcpkg integrated
(`vcpkg integrate install`); open `src/AntiDupl.sln`, build x64 Release. There are no automated tests in the
repo: each document ends with a manual test list, and `tools/` re-computes the expected numbers.

## Tools on the local machine

Claude Code runs commands through its shell, so executables are found via that shell's **PATH** (inherited
when Claude Code starts — restart it after changing PATH). Python packages are found by the interpreter
(`import ssimulacra2` works without PATH; pip's `.exe` wrappers live in the Python `Scripts` folder). Nothing
else is searched automatically, so either put tools on PATH or write their locations into the repo's
[`CLAUDE.md`](../CLAUDE.md), which local sessions read at start. Recommended native metric tools:

* `ssimulacra2.exe`, `butteraugli_main.exe` — libjxl reference builds, in `jxl-x64-windows-static.zip`
  (`bin\`) from the libjxl GitHub releases (v0.12.0 checked).
* `exiftool.exe` (for [05](05-metadata-merge.md)).
* `tools/metric_experiment.py --tool-dir <folder>` (or `ANTIDUPL_TOOL_DIRS`) also finds tools off PATH.

## Files

| File | Content |
|---|---|
| [01-difference-correctness.md](01-difference-correctness.md) | decoder bug, cache, float noise, pixel identity, display rule, area resampling |
| [02-comparison-modes.md](02-comparison-modes.md) | metric research, size study, new algorithm modes |
| [03-ui-bugs.md](03-ui-bugs.md) | view-mode reset/stacked cells, sorting |
| [04-dark-mode.md](04-dark-mode.md) | dark mode |
| [05-metadata-merge.md](05-metadata-merge.md) | delete-and-keep-metadata (AI metadata, ExifTool) |
| [06-stretch-and-ameliorations.md](06-stretch-and-ameliorations.md) | QuantSmooth spec, other improvements |
| [tools/](tools/README.md) | reproduction scripts, experiment, Butteraugli harness, ExifTool config |
