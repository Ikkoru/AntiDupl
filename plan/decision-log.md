# The decision log (`decisions.jsonl`)

The personal build records what happens to each result pair, so other programs can learn from the user's choices (T17; the settings study, [07](07-settings-study.md), and other tools of the user's). `DecisionLog` in `src/AntiDupl.NET.WinForms/DecisionLog.cs` writes it; `tools/decisions_check.py` (`read_log`, `replay`) is the reference reader.

## The file

* `decisions.jsonl` in the program's settings folder: the `user\` folder next to the personal build's program, or the folder given with `-s`. Never in a searched folder, unless the settings folder is put inside one.
* Append-only, UTF-8 without BOM, one JSON object per line, lines ending in LF. Paths are written verbatim (long paths, any Unicode; JSON escapes only what it must).
* Writing never stops the program: a line that can't be written is lost. Each search's result lines are written by the search thread in one write, before the list appears.
* Every line has `time` (local time with its offset, ISO 8601), `schema` and `event`. `schema` is 2 for the format below; lines without it are version 1, which had no `start`, `close` or `result` events, no `ignore`, `commandLineFolders` or full settings on `search`, and no group actions.

## Events

| `event` | When | Fields |
|---|---|---|
| `start` | the program opens | `version` (the product version), `built` (the program file's time, UTC: tells personal builds of one version apart), `userFolder` |
| `search` | a search ends (or is stopped) | `settings` (full, below), `folders` (searched, with subfolders), `ignore` (ignored folders), `commandLineFolders` (true when `-search` replaced the profile's folders), `images`, `pairs`, `defects`, `seconds` |
| `result` | right after each `search`, one per result, in the list's first order | `row` (0-based), `group`, `groupSize` (AntiDupl's groups of connected pairs), and the pair (below) |
| `view` | the user moves to a pair (repeats of the same pair are left out) | `row`, `rows`, the pair |
| `action` | an action is about to be applied | `action`, `target` (`Current`, `Selected`, `CurrentGroup`), `detail` (where the action takes a name: the new path of a rename, the folder of a group move, the name of a group rename), `row`, `rows`, `settings` (short), `pairs` (a list of pairs) |
| `undo`, `redo` | the user undoes or redoes the last action | none |
| `key` | a hot key or Ctrl+Z / Ctrl+Y is pressed, whatever has the focus | `key`, `hotKey` (its action), `to` and `window` (the control and window it went to), `progressWindowOpen`, `repeat` (held down) |
| `close` | the program closes | `resultsLeft` (results still in the list) |

Results loaded when the program opens (the profile's results file) are those of the last earlier `search` with `commandLineFolders` false: a `-search` run never reads or writes the profile's results file.

**A pair** has `type` (`DuplImagePair` or `DefectImage`), `difference` (unrounded, in the Difference column's units: percent for SSIM, mean square and local colour, Butteraugli's own units for Butteraugli), `transform` (`Turn_0` unless the transformed search turned or mirrored one image), `hint`, `first` and, for a pair, `second`, or `defect` for a defect. Each image has `path`, `size` (bytes), `modified` (UTC), `format`, `width`, `height`, `blockiness` and `blurring` (AntiDupl's own estimates). A pair is identified by its two paths in either order: a search puts the lesser path first, but sorting by one image's property (a *1:* or *2:* column) can swap the sides, so a `view` or `action` may name them the other way round than the `result` did.

**`hint`** is AntiDupl's own suggestion of what to do with the pair (`DeleteFirst`, `DeleteSecond`, `RenameFirstToSecond`, `RenameSecondToFirst`, or `None`). It is not a judgement of which copy is better: the user never follows it and finds it often points at the copy they keep. The build has no measured "which copy is worse" rule; the study's (`better_copy` in `tools/study_metrics.py`) can be run on the logged paths.

**`settings`** on actions: `algorithm`, `threshold`, `reducedImageSize`, and `butteraugliSize` for Butteraugli. On `search` also `checkOnEquality`, `transformedImage`, `sizeControl`, `typeControl`, `ratioControl`, `minimalImageSize`, `maximalImageSize`, `compareInsideOneFolder`, `compareInsideOneSearchPath`, `ignoreFrameWidth`, `mistakeDataBase`, `deleteToRecycleBin`.

## Actions and what they mean for a pair

| `action` | The pair's decision (`replay`) |
|---|---|
| `DeleteFirst`, `DeleteSecond`, `DeleteBoth`, `DeleteDefect` | deleted (to the Recycle Bin when `deleteToRecycleBin`) |
| `RenameFirstToSecond`, `RenameSecondToFirst` | deleted: one replaces the other under its name |
| `PerformHint` | deleted when the pair's `hint` deletes or replaces one, otherwise nothing |
| `Mistake` | mistake: not duplicates, both kept (AntiDupl remembers it when `mistakeDataBase`) |
| `RenameFirst`, `RenameSecond` (`detail`: the new path), `RenameFirstLikeSecond`, `RenameSecondLikeFirst`, `RenameCurrentGroupAs` | linked: both kept as related pictures, one renamed after the other |
| `MoveFirstToSecond`, `MoveSecondToFirst`, `MoveAndRenameFirstToSecond`, `MoveAndRenameSecondToFirst`, `MoveCurrentGroupToDirectory` | moved: both kept, one next to the other |

A pair looked at (`view`) with no action is left: kept for now, the user moved on. An `undo` takes back the last action's decisions and a `redo` applies them again; a new action clears what can be redone.
