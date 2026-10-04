# AntiDupl (Ikkoru fork) — notes for Claude Code sessions

* Work items: [`tasks.md`](tasks.md). Evidence, root causes and designs: [`plan/README.md`](plan/README.md) — read it
  before changing the comparison code, the options classes or the sorting.
* Build: Visual Studio with the .NET desktop + C++ desktop workloads (projects use the v143 toolset and
  `net10.0-windows`), vcpkg manifest mode; `src/AntiDupl.sln`, x64 Release → `bin\Release\AntiDupl.NET.WinForms.exe`.
  The first build compiles all vcpkg dependencies and takes a long time.
* **Paths with spaces/commas break the build**: the C# build events call `cmd\CopyData.cmd` and
  `src\AntiDupl.NET.Core\External.cmd` with unquoted paths (task T0). The user's checkout lives under
  `…\Coding, etc\Claude Code\…`, so fix T0 first.
* **Never run a dev build against the user's real data** (`%LOCALAPPDATA%\AntiDupl.NET\user`: settings,
  image DB, mistakes list, results). Start it with `-s "<path to ..\DevUserData>"` (folder must exist). Do not
  copy `options.xml` there — it stores an absolute path to the real profile. Test on copies of images.
* Upstream is `ermig1979/AntiDupl` (branch `master`). Keep upstreamable fixes (⬆ in `tasks.md`) on separate
  branches from `upstream/master`, one fix per branch; `plan/`, `tasks.md` and this file stay out of upstream PRs.
  The user is new to Git/GitHub (uses GitHub Desktop): explain what you do, and ask before pushing,
  opening PRs or posting anything on GitHub.

## Local layout (siblings of this repo folder)

| What | Path (relative to this repo) |
|---|---|
| Handover from the research session | `..\HANDOVER.md` |
| User's example image pairs (Examples.zip) | `..\Examples\` |
| Dev-build user data (`-s`) | `..\DevUserData\` |
| libjxl tools (`ssimulacra2.exe`, `butteraugli_main.exe`) | `..\Tools\jxl\bin\` |
| ExifTool | `..\Tools\exiftool\exiftool.exe` |
| User's AntiDupl settings (copies, reference only) | `..\reference\user-settings\` |
| Drafts for upstream issue comments | `..\reference\github-drafts\` |
| QuantSmooth / "QS Compare" script | `C:\Users\Ikkoru\Desktop\Coding, etc\Claude Code\hidpi-manga\tools\sendto\QS Compare (no menu).cmd` |
| Python | whatever `python` resolves to; install `plan\tools\requirements.txt` |
