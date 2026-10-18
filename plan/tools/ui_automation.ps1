# Helpers for driving a dev build's Windows Forms UI from PowerShell 7
# through UI Automation, for checks that need the running program (see
# README.md). Dot-source it:  . <path>\ui_automation.ps1
#
# Traps these helpers work around:
# * UI Automation's Invoke on a menu item or button that opens a modal
#   dialog returns only when the dialog closes, and calls into the program
#   from any process time out while it is pending. Open-AdOptions posts a
#   mouse click to the tool bar instead.
# * Process.CloseMainWindow can pick a tool tip that is showing (a posted
#   mouse move leaves one up). Stop-AdBuild posts WM_CLOSE to the main
#   window's own handle.
# * The Options dialog's lists offer neither SelectionPattern's selection
#   nor a useful Name: Get-AdListValue reads ValuePattern first.
# * The build is always started with -s and a scratch settings folder,
#   never on the user's real settings.
Add-Type -AssemblyName UIAutomationClient, UIAutomationTypes, System.Drawing
Add-Type @"
using System;
using System.Runtime.InteropServices;
public static class AdUiNative {
    [DllImport("user32.dll")] public static extern bool PostMessage(IntPtr h, uint m, IntPtr w, IntPtr l);
    [DllImport("user32.dll")] public static extern bool ScreenToClient(IntPtr h, ref POINT p);
    [DllImport("user32.dll")] public static extern bool PrintWindow(IntPtr h, IntPtr dc, uint f);
    [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr h, out RECT r);
    [StructLayout(LayoutKind.Sequential)] public struct POINT { public int X, Y; }
    [StructLayout(LayoutKind.Sequential)] public struct RECT { public int L, T, R, B; }
}
"@
$script:AE = [Windows.Automation.AutomationElement]
$script:CT = [Windows.Automation.ControlType]
$script:TS = [Windows.Automation.TreeScope]

function New-AdCondition($property, $value) { New-Object Windows.Automation.PropertyCondition($property, $value) }

# Starts the build with a scratch settings folder and waits for its main
# window (the one with a tool bar). Returns @(process, main window).
function Start-AdBuild([string]$Exe, [string]$s, [int]$TimeoutSeconds = 40) {
    if (-not (Test-Path -LiteralPath $s -PathType Container)) { throw "no settings folder: $s" }
    $p = Start-Process -FilePath $Exe -ArgumentList '-s', "`"$s`"" -PassThru
    $byPid = New-AdCondition $AE::ProcessIdProperty $p.Id
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    $main = $null
    while (-not $main -and (Get-Date) -lt $deadline) {
        Start-Sleep -Milliseconds 700
        try {
            $main = @($AE::RootElement.FindAll($TS::Children, $byPid)) |
                Where-Object { $_.FindFirst($TS::Children, (New-AdCondition $AE::ControlTypeProperty $CT::ToolBar)) } |
                Select-Object -First 1
        } catch {}
    }
    if (-not $main) { Stop-Process -Id $p.Id; throw "main window not found" }
    return @($p, $main)
}

# Closes the program as the user would; ends it by its process id if it
# doesn't close within the timeout, and says so.
function Stop-AdBuild($p, $main, [int]$TimeoutSeconds = 15) {
    # A WM_CLOSE right after a list was used is sometimes lost (seen after
    # choosing in the tool bar's list), so it goes again once.
    $h = [IntPtr]$main.Current.NativeWindowHandle
    [AdUiNative]::PostMessage($h, 0x0010, [IntPtr]0, [IntPtr]0) | Out-Null # WM_CLOSE
    if (-not $p.WaitForExit(5000)) { [AdUiNative]::PostMessage($h, 0x0010, [IntPtr]0, [IntPtr]0) | Out-Null }
    if (-not $p.WaitForExit($TimeoutSeconds * 1000)) {
        $env:AD_UI_STUCK_PICTURE -and (Save-AdWindowPicture $main $env:AD_UI_STUCK_PICTURE) | Out-Null
        Stop-Process -Id $p.Id; "did not close; ended by process id"
    }
}

# Posts a left click to the middle of an element in a window of its own
# (a tool bar button: pass the tool bar as $Window).
function Send-AdClick($element, $window) {
    $b = $element.Current.BoundingRectangle
    $pt = New-Object AdUiNative+POINT
    $pt.X = [int]($b.X + $b.Width / 2); $pt.Y = [int]($b.Y + $b.Height / 2)
    $h = [IntPtr]$window.Current.NativeWindowHandle
    [AdUiNative]::ScreenToClient($h, [ref]$pt) | Out-Null
    $lp = [IntPtr](($pt.Y -shl 16) -bor ($pt.X -band 0xFFFF))
    [AdUiNative]::PostMessage($h, 0x200, [IntPtr]0, $lp) | Out-Null # WM_MOUSEMOVE: the item under the pointer
    [AdUiNative]::PostMessage($h, 0x201, [IntPtr]1, $lp) | Out-Null # WM_LBUTTONDOWN
    [AdUiNative]::PostMessage($h, 0x202, [IntPtr]0, $lp) | Out-Null # WM_LBUTTONUP
}

# Opens Search > Options through the tool bar's Options button (its sixth
# button) and returns the dialog.
function Open-AdOptions($p, $main, [int]$TimeoutSeconds = 30) {
    $toolbar = $main.FindFirst($TS::Children, (New-AdCondition $AE::ControlTypeProperty $CT::ToolBar))
    $button = @($toolbar.FindAll($TS::Children, (New-AdCondition $AE::ControlTypeProperty $CT::Button)))[5]
    Send-AdClick $button $toolbar
    $isWindow = New-AdCondition $AE::ControlTypeProperty $CT::Window
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        Start-Sleep -Seconds 1
        try {
            # The dialog is a window inside the main window in UI Automation's tree.
            $dialog = @($main.FindAll($TS::Children, $isWindow)) | Where-Object { $_.Current.Name -eq 'Options' } | Select-Object -First 1
            if ($dialog) { return $dialog }
        } catch {}
    }
    throw "options dialog not found"
}

# Presses a dialog button by posting BM_CLICK to it.
function Send-AdButton($dialog, [string]$Name) {
    $button = $dialog.FindFirst($TS::Descendants, (New-Object Windows.Automation.AndCondition(
        (New-AdCondition $AE::NameProperty $Name), (New-AdCondition $AE::ControlTypeProperty $CT::Button))))
    if (-not $button) { throw "no button '$Name'" }
    [AdUiNative]::PostMessage([IntPtr]$button.Current.NativeWindowHandle, 0x00F5, [IntPtr]0, [IntPtr]0) | Out-Null
}

function Get-AdLists($root) { @($root.FindAll($TS::Descendants, (New-AdCondition $AE::ControlTypeProperty $CT::ComboBox))) }

# The item names of a drop-down list (opened and closed again to read them).
function Get-AdListItems($combo) {
    $ec = $combo.GetCurrentPattern([Windows.Automation.ExpandCollapsePattern]::Pattern)
    $ec.Expand(); Start-Sleep -Milliseconds 400
    $names = @($combo.FindAll($TS::Descendants, (New-AdCondition $AE::ControlTypeProperty $CT::ListItem)) | ForEach-Object { $_.Current.Name })
    try { $ec.Collapse() } catch {}
    Start-Sleep -Milliseconds 300
    $names
}

function Select-AdListItem($combo, [string]$Name) {
    $ec = $combo.GetCurrentPattern([Windows.Automation.ExpandCollapsePattern]::Pattern)
    $ec.Expand(); Start-Sleep -Milliseconds 400
    $item = @($combo.FindAll($TS::Descendants, (New-AdCondition $AE::ControlTypeProperty $CT::ListItem))) |
        Where-Object { $_.Current.Name -eq $Name } | Select-Object -First 1
    if (-not $item) { try { $ec.Collapse() } catch {}; throw "no item '$Name'" }
    $item.GetCurrentPattern([Windows.Automation.SelectionItemPattern]::Pattern).Select()
    try { $ec.Collapse() } catch {}
    Start-Sleep -Milliseconds 600
}

function Get-AdListValue($combo) {
    $o = $null
    if ($combo.TryGetCurrentPattern([Windows.Automation.ValuePattern]::Pattern, [ref]$o)) { return $o.Current.Value }
    if ($combo.TryGetCurrentPattern([Windows.Automation.SelectionPattern]::Pattern, [ref]$o)) {
        $sel = $o.Current.GetSelection()
        if ($sel.Count) { return $sel[0].Current.Name }
    }
    $combo.Current.Name
}

# A picture of a window as it is drawn (PrintWindow: windows on top don't matter).
function Save-AdWindowPicture($element, [string]$Path) {
    $h = [IntPtr]$element.Current.NativeWindowHandle
    $r = New-Object AdUiNative+RECT
    [AdUiNative]::GetWindowRect($h, [ref]$r) | Out-Null
    $bmp = New-Object System.Drawing.Bitmap ($r.R - $r.L), ($r.B - $r.T)
    $g = [System.Drawing.Graphics]::FromImage($bmp)
    $dc = $g.GetHdc(); [AdUiNative]::PrintWindow($h, $dc, 2) | Out-Null; $g.ReleaseHdc($dc); $g.Dispose()
    $bmp.Save($Path)
}

# The saved profile's compare options (the scratch folder's default.xml).
function Read-AdProfile([string]$s) {
    Get-ChildItem -LiteralPath $s -Recurse -Filter default.xml | ForEach-Object {
        $x = [xml](Get-Content -LiteralPath $_.FullName -Raw)
        [pscustomobject]@{
            algorithmComparing = $x.SelectSingleNode('//algorithmComparing').InnerText
            thresholdDifference = $x.SelectSingleNode('//thresholdDifference').InnerText
            butteraugliSize = $x.SelectSingleNode('//butteraugliSize').InnerText
        }
    }
}
