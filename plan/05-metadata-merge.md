# 05 — Stretch: "Delete, but add its metadata to the other image"

User decision: copy **missing tags only** (never overwrite what the kept file already has), **including the generation data written by AI tools** (prompts, settings, workflows). Must keep undo working.

## Where AI tools put their data (and what ExifTool calls it)

Verified by creating fixtures and reading them with ExifTool 13.59 (`tools/antidupl.ExifTool_config`):

| Tool | PNG | JPEG / WebP |
|---|---|---|
| AUTOMATIC1111 / Forge / reForge | `tEXt parameters` → `PNG:Parameters` | EXIF `UserComment` |
| ComfyUI | `tEXt/zTXt prompt`, `workflow` (JSON) → `PNG:Prompt`, `PNG:Workflow` | WebP: EXIF `Make`="workflow:…", `Model`="prompt:…" |
| NovelAI | `Title`, `Description`, `Software`, `Source`, `Comment` (JSON) + a signed copy hidden in the **alpha-channel LSBs** ("stealth pnginfo") | — |
| InvokeAI | `invokeai_metadata`, `invokeai_graph` (older: `sd-metadata`, `Dream`) | — |
| Fooocus / SwarmUI | `parameters` (+ `fooocus_scheme`) | EXIF `UserComment` |
| DALL·E / Firefly / Bing etc. | C2PA manifest (JUMBF, `caBX` chunk) + XMP `DigitalSourceType` | C2PA in APP11 + XMP |

## Verified ExifTool behaviour

* `exiftool -tagsfromfile SRC -all:all -wm cg DST` copies tags **missing** in DST and leaves existing values alone (`-wm cg` = create only). Works PNG→PNG for `Parameters` and the NovelAI keys (byte-exact, multi-line prompts intact), JPEG→PNG for EXIF/XMP.
* ComfyUI/InvokeAI/Fooocus keywords are readable but **not writable** without a config ("No writable tags set"). With `-config antidupl.ExifTool_config` (defines `prompt`, `workflow`, `invokeai_metadata`, `invokeai_graph`, `sd-metadata`, `Dream`, `fooocus_scheme`, `generation_data` as PNG text tags) they copy with their exact lower-case keywords — ComfyUI can load the workflow from the kept PNG.
* Cross-format needs explicit mappings; `-all:all` won't move PNG text into JPEG. Verified: `"-EXIF:UserComment<PNG:Parameters"` into JPEG and WebP keeps newlines, is stored with an `ASCII` charset header, and is read back by `piexif.helper.UserComment.load` (what A1111's PNG-Info uses for JPEG/WebP). Test non-ASCII prompts (ExifTool should switch to the `UNICODE` charset).
* **Not transferable:** C2PA manifests (bound to the original pixels/bytes, copying invalidates them) and NovelAI stealth info (lives in pixels). Warn instead.

## Design

**Actions:** "Delete first → keep its metadata in second" and the mirror; suggested hotkeys **Shift+NumPad1 / Shift+NumPad2** (the user deletes with NumPad1/2), pair-preview toolbar buttons and context-menu items. New option: ExifTool path (like `imageDiffExecutablePath`), plus the config file shipped in `data/` next to the exe.

**Flow** (C# side, wrapping the existing core delete — hook in [ResultsListView.MakeAction](../src/AntiDupl.NET.WinForms/GUIControl/ResultsListView.cs#L269) / `ProgressForm`):

1. `src` = file to delete, `dst` = file to keep.
2. Backup `dst` → hidden `~~adm%08x~~<name>` in the same folder (same idea as the core's recycle naming `~~adt%08x~~`, [adRecycleBin.cpp:33](../src/AntiDupl/adRecycleBin.cpp#L33)).
3. Run `exiftool -config "<data>\antidupl.ExifTool_config" -overwrite_original -P -m -q -tagsfromfile "<src>" -all:all -wm cg [mappings] "<dst>"` (`-P` keeps dst's modified time). Mappings when formats differ, all with `-wm cg`:
   * PNG `Parameters` → JPEG/WebP `EXIF:UserComment`
   * PNG `Description`/`Comment` (NovelAI) → `XMP-dc:Description` / `EXIF:UserComment` if still empty
   * ComfyUI `workflow`/`prompt` → WebP: `EXIF:Make<workflow:$PNG:Workflow`, `EXIF:Model<prompt:$PNG:Prompt`; JPEG: best effort (no ComfyUI convention) — store in XMP, and warn
4. Only if ExifTool exits 0: run the normal core delete of `src` (undoable, recycle-bin aware).
5. Keep a C# list of merge records `{coreUndoStep, dst, backup}`. **Undo**: restore `dst` from its backup, then call the core undo. **Redo**: core redo, then re-run step 3. Drop (delete) backups when the core's undo queue (`undoQueueSize`) forgets the step or on exit.
6. If `src` carries C2PA or NovelAI stealth data, show a one-line warning ("… will be lost").

*Alternative:* implement it in the core as new `adLocalActionType`s with a `modifiedImages` list in `TChange` so undo/redo stay in one place; cleaner, but needs ExifTool invocation and a path option in C++.

**Side effects:** `dst`'s size/CRC change → it is re-read on the next search (metadata only, so it stays pixel-identical to its duplicates).

## Tests

PNG(A1111)→PNG, PNG(ComfyUI)→PNG (needs the config), PNG(NovelAI)→PNG, PNG(A1111)→JPEG/WebP, JPEG(EXIF+XMP)→PNG; kept file already has a different `Parameters` → unchanged; undo restores both files byte-exact; redo re-applies; ExifTool missing/failing → nothing is deleted.
