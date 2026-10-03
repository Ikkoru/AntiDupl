# AntiDupl (Ikkoru fork) — notes for Claude Code sessions

* Work items: [`tasks.md`](tasks.md). Evidence, root causes and designs: [`plan/README.md`](plan/README.md) — read it
  before changing the comparison code, the options classes or the sorting.
* Build: Visual Studio (v143 toolset), .NET 10 SDK, vcpkg manifest mode; `src/AntiDupl.sln`, x64 Release.
  No automated tests: use the manual test list at the end of each `plan/0*.md` and `plan/tools/` scripts.
* Upstream is `ermig1979/AntiDupl` (branch `master`). Keep upstreamable fixes (⬆ in `tasks.md`) on separate
  branches from `master`, one fix per branch; `plan/`, `tasks.md` and this file stay out of upstream PRs.

## Local tools (fill in — commands are only found via PATH)

| Tool | Path |
|---|---|
| Python with `plan/tools/requirements.txt` | `…` |
| libjxl tools (`ssimulacra2.exe`, `butteraugli_main.exe`) | `…\jxl-x64-windows-static\bin` |
| ExifTool | `…\exiftool.exe` |
| QuantSmooth / "QS Compare" script | `C:\Users\Ikkoru\Desktop\Coding, etc\Claude Code\hidpi-manga\tools\sendto\QS Compare (no menu).cmd` |
| Test images (user's Examples.zip) | `…` |
