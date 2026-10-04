# 04 — Dark mode (WinForms, Windows 11)

Upstream request: [ermig1979/AntiDupl#115](https://github.com/ermig1979/AntiDupl/issues/115) (2020, open). The user runs Windows 11.

## Approach: .NET 10's built-in color mode

The WinForms app targets `net10.0-windows7.0` ([AntiDupl.NET.WinForms.csproj](../src/AntiDupl.NET.WinForms/AntiDupl.NET.WinForms.csproj)). Since .NET 10, `Application.SetColorMode(SystemColorMode.Classic | Dark | System)` is no longer experimental (no `WFO5001` suppression needed). Verified in the dotnet/winforms `release/10.0` sources:

* `SetColorMode` switches `SystemColors` to the alternative (dark) set, so every control using default/system colours follows automatically.
* Top-level windows get dark title bars (`DWMWA_USE_IMMERSIVE_DARK_MODE`, `Control.PrepareDarkMode`).
* `ToolStripSystemRenderer` swaps in `ToolStripSystemDarkModeRenderer` when dark mode is on — AntiDupl's menus/toolbars all use `RenderMode = ToolStripRenderMode.System`, so they are covered.
* It must be called **before any UI is created**; `System` follows the OS setting at start-up only (Win 11+).
* `DataGridView` has no dark-specific code: cells use `SystemColors` (fine), column headers are drawn with visual styles unless `EnableHeadersVisualStyles = false`.

## Steps

1. **Setting.** Add `public SystemColorMode ColorMode = SystemColorMode.System;` (or own enum) to [Options.cs](../src/AntiDupl.NET.WinForms/Options.cs) — copy ctor, `CopyTo`, `Equals` too — and a *View → Theme → System / Light / Dark* menu (radio items like `ViewModeMenuItem`). Changing it shows "restart to apply".
2. **Apply early.** Today `MainForm` loads the options itself ([MainForm.cs:57](../src/AntiDupl.NET.WinForms/Form/MainForm.cs#L57)). Load them in [Program.cs](../src/AntiDupl.NET.WinForms/Program.cs#L53) instead: `var options = Options.Load(); Application.SetColorMode(options.ColorMode); Application.Run(new MainForm(options));`
3. **Theme helper.** `static class ThemeColors` returning light/dark values based on `Application.IsDarkModeEnabled`, and replace the hard-coded colours:

   | Where | Today | Use |
   |---|---|---|
   | [ResultsListView.cs:170](../src/AntiDupl.NET.WinForms/GUIControl/ResultsListView.cs#L170) | `BackgroundColor = Color.White` | `SystemColors.Window` |
   | [ResultRowSetter.cs:329](../src/AntiDupl.NET.WinForms/ResultRowSetter.cs#L329) | identical = `Color.LightGreen` (poor contrast on white) | `ThemeColors.Identical` (light: `#1B7F2A`, dark: `LightGreen`) |
   | ResultRowSetter.cs:530-568, [ImagePreviewPanel.cs:223-251](../src/AntiDupl.NET.WinForms/GUIControl/ImagePreviewPanel.cs#L223) | "worse" value = `Color.Red` | `ThemeColors.Worse` (dark: `#FF7070`) |
   | [PictureBoxPanel.cs:102](../src/AntiDupl.NET.WinForms/GUIControl/PictureBoxPanel.cs#L102) | preview background `Color.DarkGray` | `ThemeColors.PreviewBackground` (dark: `#202020`) |
   | [DataGridViewCustomRow.cs:65-68](../src/AntiDupl.NET.WinForms/DataGridViewCustomRow.cs#L65) | current-row focus rect white + black dots | `SystemColors.Window` + `SystemColors.WindowText` |
   | [DataGridViewDoubleTextBoxCell.cs:42-43](../src/AntiDupl.NET.WinForms/DataGridViewDoubleTextBoxCell.cs#L42) | separator `LightGray`, marker `Red` | `SystemColors.ControlDark`, `ThemeColors.Worse` |
   | [Resources.cs:101-113](../src/AntiDupl.NET.WinForms/Resources.cs#L101) | checked-item dot drawn black (invisible on dark menus; used by ViewMode/Language menus) | draw with `SystemColors.MenuText` |
   | [ResultsPreviewDuplPair.cs:166](../src/AntiDupl.NET.WinForms/GUIControl/ResultsPreviewDuplPair.cs#L166) | hint button tint = mix(BackColor, Red) | OK (derives from BackColor); check contrast |
   | [ComplexProgressBar.cs](../src/AntiDupl.NET.WinForms/GUIControl/ComplexProgressBar.cs) | mixes Fore/BackColor | OK if Fore/Back are system colours; check |
   | `MainMenu.cs:104`, `MainToolStrip.cs:89`, `ResultsPreviewBase.cs:73` | `SystemColors.Control` | OK (remapped) |

4. **Grid headers.** In `ResultsListView.InitializeComponents`: `EnableHeadersVisualStyles = !Application.IsDarkModeEnabled;` and set `ColumnHeadersDefaultCellStyle.BackColor/ForeColor` and `GridColor` from `SystemColors`.
5. **Verify every surface** (things the framework may leave light): Options dialog `TabControl` ([CoreOptionsForm.cs:171](../src/AntiDupl.NET.WinForms/Form/CoreOptionsForm.cs#L171)) — owner-draw the tab headers if they stay light; combo-box drop-downs; `NumericUpDown`; check boxes; grid scrollbars; tooltips; About panel; Paths/HotKeys/Columns/Progress/StartFinish forms; toolbar PNG icons on a dark background. Native folder pickers follow the OS theme on their own.

## Acceptance

Light mode looks exactly as before except the identical-difference green is darker (readable). Dark mode: no white surfaces left in the main window, Options (all tabs), Paths, Hot keys, Columns, Progress, About; the checked-item dots and focus rectangle are visible; title bars dark.
