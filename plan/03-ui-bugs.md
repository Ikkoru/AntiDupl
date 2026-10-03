# 03 — View-mode reset, stacked cells, janky sorting

## Bug H — "Horizontal pairs" resets / rows show two stacked values per cell

**Root cause:** pressing **Cancel** in *Search → Options* replaces the live results-options object.

* [CoreOptionsForm.cs:147](../src/AntiDupl.NET.WinForms/Form/CoreOptionsForm.cs#L147) snapshots
  `m_oldResultsOptions = m_options.resultsOptions.Clone();`
* While the dialog is open, highlight settings are applied live: `OnHighlightChanged` (lines 522-538)
  writes them straight into `m_options.resultsOptions` and raises the change event. The form has no
  `FormClosing` handler, so closing with ✕ keeps those live edits.
* [CoreOptionsForm.cs:879](../src/AntiDupl.NET.WinForms/Form/CoreOptionsForm.cs#L879) on Cancel:
  `m_options.resultsOptions = m_oldResultsOptions;` — a **different object**.
* The clone comes from the copy constructor
  [ResultsOptions.cs:324](../src/AntiDupl.NET.WinForms/ResultsOptions.cs#L324), which does **not** copy
  `m_viewMode` (field initialiser = `VerticalPairTable`), `StretchSmallImages`, `ProportionalImageSize` or
  `ShowNeighboursImages`, and of course carries none of the event subscriptions
  (`OnViewModeChange` → `MainSplitContainer`, `MainToolStrip`, `ViewModeMenuItem`).

**Consequences (exactly the user's symptoms):**

1. The grid keeps its horizontal columns (`ResultsListView.m_viewMode` is still Horizontal), but
   [ResultRowSetter.cs:243/395](../src/AntiDupl.NET.WinForms/ResultRowSetter.cs#L243) builds rows from
   `m_options.resultsOptions.viewMode` = Vertical → vertical `DataGridViewDoubleTextBoxCell`s (two values
   stacked) inside horizontal columns.
2. On exit `options.xml` is saved with `<viewMode>VerticalPairTable</viewMode>` → next start "resets".
3. Until restart, View → mode changes no longer reach the UI (no subscribers on the new object);
   highlight/stretch/proportional/neighbour settings silently revert to defaults.

Also: [Options.cs:106-110](../src/AntiDupl.NET.WinForms/Options.cs#L106) returns `new Options()` on *any*
deserialisation error, silently resetting everything (another possible "reset" source).

**Fix:**

* `ResultsOptions` copy constructor: copy **all** state (`m_viewMode` field directly — no event —, the three
  image-view flags, all highlight fields). Add `CopyHighlightTo(ResultsOptions dst)` (or a general
  `CopyAllTo`) and extend `Equals` accordingly. `CopyTo` (used by the column forms) may stay columns-only.
* `CoreOptionsForm.OnCancelButtonClick`: never assign the object; restore values into the live one and raise
  the change event:
  ```csharp
  private void OnCancelButtonClick(object sender, EventArgs e)
  {
      m_oldResultsOptions.CopyHighlightTo(m_options.resultsOptions);
      m_options.resultsOptions.RaiseEventOnHighlightDifferenceChange();
      Close();
  }
  ```
  Do the same in `FormClosing` when the dialog is closed with the window's ✕ (today live changes stay).
* Defensive: `ResultRowSetter` should build rows for the grid's **actual** mode — expose
  `ResultsListView.CurrentViewMode` (`m_viewMode`) and use it at lines 243/395 (and in
  `ClipboardContentBuilder`), so a mismatch can never produce stacked cells again.
* `Options.Load()`: on failure, copy the bad file to `options.xml.bad` and show one message instead of
  silently defaulting.

**Test:** horizontal mode → Options → change a highlight value → Cancel → rows still single-line; switch
View modes → UI follows; restart → still horizontal; highlight value reverted. Repeat with ✕ instead of Cancel.

**Workaround in the current release:** use **OK** (not Cancel/✕) in the Options dialog. After a Cancel,
re-select *View → Table of horizontal pairs* before closing the app.

## Bug I — Sorting is janky; earlier sorts influence later ones

Three separate causes in the core:

1. **Every pair gets left/right-swapped on most sorts.**
   [adUndoRedoTypes.cpp:71-83](../src/AntiDupl/adUndoRedoTypes.cpp#L71):
   ```cpp
   if(pResult->type == AD_RESULT_DUPL_IMAGE_PAIR &&
       !TResult::ImageInfoLesser(pResult->first, pResult->second, sortType, increasing))
       pResult->Swap();
   ```
   `ImageInfoLesser` ([adResult.cpp:63-118](../src/AntiDupl/adResult.cpp#L63)) only knows the
   `BySorted*` types (1-12, used by the *vertical* table) and returns `false` for everything else. The
   horizontal table sends `ByFirst*`/`BySecond*` (13-36), and both tables send `ByDifference` (38), group,
   hint … → `!false` → **all pairs are swapped on every such sort**. Clicking "First directory" therefore
   moves each pair's *other* file into the first column before sorting; clicking again swaps back — the
   column literally alternates between the two folders. For `BySorted*` types ties (`!(a<b)` when equal, e.g.
   both files in the same folder) also swap every time.
2. **Unstable sort without tie-breakers.** `std::sort` + a single-key comparator: rows with equal keys (most
   rows when sorting by folder) come out in an order that depends on the previous order — the user's "past
   sort actions affect the present sort order".
3. **Plain code-unit string order.** [`TPath::Compare`](../src/AntiDupl/adPath.cpp#L134) compares characters,
   so `…_p10.jpg` sorts before `…_p2.jpg` (Pixiv page numbers), unlike Explorer.

All three date back to the 2013 import (not a regression).

**Fix:**

```cpp
static bool IsSortedType(TSortType t) { return t >= AD_SORT_BY_SORTED_PATH && t <= AD_SORT_BY_SORTED_BLURRING; }

void TUndoRedoStage::Sort(TSortType sortType, bool increasing)
{
    if (IsSortedType(sortType))                       // vertical table: put the "lesser" file first
        for (TResultPtr p : results)
            if (p->type == AD_RESULT_DUPL_IMAGE_PAIR &&
                TResult::ImageInfoLesser(p->second, p->first, sortType, increasing))   // strictly
                p->Swap();
    std::stable_sort(results.begin(), results.end(), TResultPtrLesser(sortType, increasing));
    UpdateCurrentIndex();
}
```

* Rewrite `TResultPtrLesser` as a 3-way primary comparison; on ties fall back to a fixed chain that ignores
  the sort direction: `difference ↑ → first path ↑ → second path ↑ → id ↑`. This is a total order, so the
  result no longer depends on history (stable_sort is then just belt and braces).
* Display sorts (name/directory/path) use natural order: `StrCmpLogicalW` (`shlwapi.lib`) on
  `TPath::Original()`. Keep `TPath::Compare` for the internal sorted containers (search-path lookup,
  image-DB index ranges) — their on-disk ordering assumptions must not change.

**Test:** horizontal table: click *First directory* twice → the first column keeps the same files and only
the order flips; click *Difference* → no pair changes sides; any sort applied twice from different starting
orders gives identical row order; `x_p2` sorts before `x_p10`.
