# The decision log (`decisions.jsonl`)

The personal build records what happens to each result pair, so other programs can learn from the user's choices (T17; the settings study, [07](07-settings-study.md), and other tools of the user's). `DecisionLog` in `src/AntiDupl.NET.WinForms/DecisionLog.cs` writes it; `tools/decisions_check.py` (`read_log`, `replay`) is the reference reader.

## The file

* `decisions.jsonl` in the program's settings folder: the `user\` folder next to the personal build's program, or the folder given with `-s`. Never in a searched folder, unless the settings folder is put inside one.
* Append-only: never rotated or trimmed, since other programs read past lines (`DecisionLog.Write` opens it only with `FileMode.Append`). UTF-8 without BOM, one JSON object per line, lines ending in LF. Paths are written verbatim (long paths, any Unicode; JSON escapes only what it must).
* Writing never stops the program: a line that can't be written is lost.
* Every line has `time` (local time with its offset, ISO 8601), `schema` and `event`. `schema` is 4 for the format below. Version 3 wrote the first 10,000 results of a search as `result` lines right after its `search` line, whose `resultLines` said how many; version 2 all of them, up to the core's limit of 100,000. Those lines were 98 % of the log and nothing read them: `tools/log_strip.py` takes them out of an existing log, keeping the original compressed beside it, and leaves every other line as it was. Version 1 (lines without `schema`) had no `start` or `close` events, no `ignore`, `commandLineFolders` or full settings on `search`, and no group actions. In versions 1 and 2, and in version 3 before the build of 2026-11-03, an undo or redo by Ctrl+Z or Ctrl+Y in the results list wrote no `undo` or `redo` (only the menu did): `replay` counts such a key press on the list as one.

## Events

| `event` | When | Fields |
|---|---|---|
| `start` | the program opens | `version` (the product version), `built` (the program file's time, UTC: tells personal builds of one version apart), `userFolder` |
| `search` | a search ends (or is stopped) | `settings` (full, below), `folders` (searched, with subfolders), `ignore` (ignored folders), `commandLineFolders` (true when `-search` replaced the profile's folders), `images`, `pairs`, `defects`, `seconds` |
| `view` | the user moves to a pair (repeats of the same pair are left out) | `row`, `rows`, the pair |
| `action` | an action is about to be applied | `action`, `target` (`Current`, `Selected`, `CurrentGroup`), `detail` (where the action takes a name: the new path of a rename, the folder of a group move, the name of a group rename), `row`, `rows`, `settings` (short), `pairs` (a list of pairs) |
| `undo`, `redo` | the user undoes or redoes the last action | none |
| `key` | a hot key or Ctrl+Z / Ctrl+Y is pressed, whatever has the focus | `key`, `hotKey` (its action), `to` and `window` (the control and window it went to), `progressWindowOpen`, `repeat` (held down) |
| `close` | the program closes | `resultsLeft` (results still in the list) |

Results loaded when the program opens (the profile's results file) are those of the last earlier `search` with `commandLineFolders` false: a `-search` run never reads or writes the profile's results file.

**A pair** has `type` (`DuplImagePair` or `DefectImage`), `difference` (unrounded, in the Difference column's units: percent for SSIM, mean square and local colour, Butteraugli's own units for `Butteraugli` and `ButteraugliAligned`), `transform` (`Turn_0` unless the transformed search turned or mirrored one image), `hint`, `first` and, for a pair, `second`, or `defect` for a defect. Each image has `path`, `size` (bytes), `modified` (UTC), `format`, `width`, `height`, `blockiness` and `blurring` (AntiDupl's own estimates). A pair is identified by its two paths in either order: a search puts the lesser path first, but sorting by one image's property (a *1:* or *2:* column) can swap the sides, so one `view` or `action` may name them the other way round than another.

**`hint`** is AntiDupl's own suggestion of what to do with the pair (`DeleteFirst`, `DeleteSecond`, `RenameFirstToSecond`, `RenameSecondToFirst`, or `None`). It is not a judgement of which copy is better: the user never follows it and finds it often points at the copy they keep. The build has no measured "which copy is worse" rule; the study's (`better_copy` in `tools/settings_study.py`) can be run on the logged paths.

**`settings`** on actions: `algorithm`, `threshold`, `reducedImageSize`, and `butteraugliSize` for both Butteraugli algorithms. On `search` also `checkOnEquality`, `transformedImage`, `shiftedImage`, `sizeControl`, `typeControl`, `ratioControl`, `minimalImageSize`, `maximalImageSize`, `compareInsideOneFolder`, `compareInsideOneSearchPath`, `ignoreFrameWidth`, `mistakeDataBase`, `deleteToRecycleBin`.

## Actions and what they mean for a pair

| `action` | The pair's decision (`replay`) |
|---|---|
| `DeleteFirst`, `DeleteSecond`, `DeleteBoth`, `DeleteDefect` | deleted (to the Recycle Bin when `deleteToRecycleBin`) |
| `RenameFirstToSecond`, `RenameSecondToFirst` | deleted: one replaces the other under its name |
| `PerformHint` | deleted when the pair's `hint` deletes or replaces one, otherwise nothing |
| `Mistake` | mistake: not duplicates, both kept (AntiDupl remembers it when `mistakeDataBase`) |
| `RenameFirst`, `RenameSecond` (`detail`: the new path), `RenameFirstLikeSecond`, `RenameSecondLikeFirst`, `RenameCurrentGroupAs` | linked: both kept as related pictures, one renamed after the other |
| `MoveFirstToSecond`, `MoveSecondToFirst`, `MoveAndRenameFirstToSecond`, `MoveAndRenameSecondToFirst`, `MoveCurrentGroupToDirectory` | moved: both kept, one next to the other |

A pair looked at (`view`) with no action is left: kept for now, the user moved on. An `undo` takes back the last action's decisions and a `redo` applies them again; a new action clears what can be redone, and a new `search` or `start` leaves nothing to undo.
