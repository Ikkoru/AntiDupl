# Checks a build's decision log and hot-key focus in a new scratch settings
# folder (PowerShell 7; it types a real Ctrl+Z, so the program comes to the
# front): (1) after the tool bar's threshold list opens and closes, the
# focus is back on the results list; (2) Ctrl+Z typed after a mistake by
# hot key writes an "undo" line; (3) a search with more results than
# DecisionLog.RESULT_LINES_MAX writes that many result lines and says so.
# The profile asks for SSIM at 50 %. Prints one line per check, PASS or
# FAIL; a build before these fixes fails all three.
#   ui_decision_log_check.ps1 -Exe <exe> -s <new scratch folder> -Search <folder>
# -Search must give over 10,000 pairs: 200 copies of one picture do.
param([string]$Exe, [string]$s, [string]$Search)
. (Join-Path $PSScriptRoot 'ui_automation.ps1')
Add-Type -AssemblyName Microsoft.VisualBasic
Add-Type -Namespace AdLogCheck -Name Kb -MemberDefinition @'
[DllImport("user32.dll")] public static extern void keybd_event(byte vk, byte scan, uint flags, System.UIntPtr extra);
'@
function Send-CtrlZ {
    [AdLogCheck.Kb]::keybd_event(0x11, 0, 0, [UIntPtr]::Zero)   # Ctrl down
    [AdLogCheck.Kb]::keybd_event(0x5A, 0, 0, [UIntPtr]::Zero)   # Z down
    [AdLogCheck.Kb]::keybd_event(0x5A, 0, 2, [UIntPtr]::Zero)   # Z up
    [AdLogCheck.Kb]::keybd_event(0x11, 0, 2, [UIntPtr]::Zero)   # Ctrl up
}
try {
    # First start: writes the scratch profile, which then asks for SSIM at 50 %.
    $p, $main = Start-AdBuild $Exe $s
    Stop-AdBuild $p $main
    $profile = Get-ChildItem -LiteralPath $s -Recurse -Filter default.xml | Select-Object -First 1
    $x = [xml](Get-Content -LiteralPath $profile.FullName -Raw -Encoding utf8)
    # The profile holds each setting twice (field and property); both.
    foreach ($name in 'algorithmComparing', 'AlgorithmComparing') { $x.SelectSingleNode("//compareOptions/$name").InnerText = 'SSIM' }
    foreach ($name in 'thresholdDifference', 'ThresholdDifference') { $x.SelectSingleNode("//compareOptions/$name").InnerText = '50' }
    $x.Save($profile.FullName)
    $logFile = Join-Path $s 'decisions.jsonl'
    $searchesBefore = @(Get-Content -LiteralPath $logFile -Encoding utf8 | Where-Object { $_ -match '"event":"search"' }).Count

    $p = Start-Process -FilePath $Exe -ArgumentList '-s', "`"$s`"", '-search', "`"$Search`"", '-start' -PassThru
    $script:AdStarted.Add($p)
    $byPid = New-AdCondition $AE::ProcessIdProperty $p.Id
    # The search is over once its line is in the log (the search thread
    # writes it just before the list fills).
    for ($i = 0; $i -lt 600; $i++) {
        Start-Sleep -Seconds 1
        $n = @(Get-Content -LiteralPath $logFile -Encoding utf8 | Where-Object { $_ -match '"event":"search"' }).Count
        if ($n -gt $searchesBefore) { break }
    }
    if ($n -le $searchesBefore) { throw 'the search did not finish' }
    Start-Sleep -Seconds 4
    $main = $null
    for ($i = 0; $i -lt 30 -and -not $main; $i++) {
        try {
            $main = @($AE::RootElement.FindAll($TS::Children, $byPid)) | Where-Object { $_.FindFirst($TS::Children, (New-AdCondition $AE::ControlTypeProperty $CT::ToolBar)) } | Select-Object -First 1
        } catch { Start-Sleep -Seconds 1 }
    }
    $grid = $main.FindFirst($TS::Descendants, (New-AdCondition $AE::ControlTypeProperty $CT::DataGrid))
    $toolbar = $main.FindFirst($TS::Children, (New-AdCondition $AE::ControlTypeProperty $CT::ToolBar))
    $combo = @($toolbar.FindAll($TS::Children, (New-AdCondition $AE::ControlTypeProperty $CT::ComboBox)))[0]

    # (1) Focus after the threshold list opens and closes.
    [Microsoft.VisualBasic.Interaction]::AppActivate($p.Id)
    Start-Sleep -Milliseconds 500
    $ec = $combo.GetCurrentPattern([Windows.Automation.ExpandCollapsePattern]::Pattern)
    $ec.Expand(); Start-Sleep -Milliseconds 600; $ec.Collapse(); Start-Sleep -Milliseconds 800
    $focused = [Windows.Automation.AutomationElement]::FocusedElement
    $onGrid = $false
    $e = $focused
    $walker = [Windows.Automation.TreeWalker]::RawViewWalker
    for ($i = 0; $i -lt 6 -and $e; $i++) { if ($e.Current.ControlType -eq $CT::DataGrid) { $onGrid = $true }; $e = $walker.GetParent($e) }
    "{0} (1) focus after the threshold list closed: {1} '{2}'" -f $(if ($onGrid) { 'PASS' } else { 'FAIL' }), $focused.Current.ControlType.ProgrammaticName, $focused.Current.ClassName

    # (2) A mistake by hot key, then a real Ctrl+Z.
    [AdUiNative]::PostMessage([IntPtr]$grid.Current.NativeWindowHandle, 0x0100, [IntPtr]0x65, [IntPtr]1) | Out-Null
    Start-Sleep -Seconds 2
    $grid.SetFocus()
    [Microsoft.VisualBasic.Interaction]::AppActivate($p.Id)
    Start-Sleep -Milliseconds 500
    Send-CtrlZ
    Start-Sleep -Seconds 2
    Stop-AdBuild $p $main
} finally { Stop-AdStrays }

$events = Get-Content -LiteralPath (Join-Path $s 'decisions.jsonl') -Encoding utf8 | Where-Object { $_ -notmatch '"event":"result"' } | ForEach-Object { $_ | ConvertFrom-Json }
$tail = @($events | Where-Object { $_.event -in 'action', 'undo', 'key' } | Select-Object -Last 4)
$undo = @($events | Where-Object { $_.event -eq 'undo' }).Count
"{0} (2) after the mistake and Ctrl+Z: {1}" -f $(if ($undo -ge 1) { 'PASS' } else { 'FAIL' }), (($tail | ForEach-Object { if ($_.event -eq 'key') { "key $($_.hotKey)" } elseif ($_.event -eq 'action') { "action $($_.action)" } else { $_.event } }) -join ', ')

$searchEvent = @($events | Where-Object { $_.event -eq 'search' })[-1]
$resultCount = @(Get-Content -LiteralPath (Join-Path $s 'decisions.jsonl') -Encoding utf8 | Where-Object { $_ -match '"event":"result"' }).Count
$ok = ($searchEvent.pairs -gt 10000) -and ($resultCount -eq 10000) -and ($searchEvent.resultLines -eq 10000)
"{0} (3) search pairs {1}, resultLines {2}, result lines written {3}" -f $(if ($ok) { 'PASS' } else { 'FAIL' }), $searchEvent.pairs, $searchEvent.resultLines, $resultCount
