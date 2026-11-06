# Paths > Add Folder with two folders chosen at once: each becomes a search
# path of its own (PASS/FAIL). The listed search folder is removed from disk
# before the dialog opens, so that it opens in the program's folder: chosen
# inside a listed folder, the two would be dropped as already covered, and
# the check could not tell that from the dialog returning nothing.
#
#   pwsh -File ui_add_folders_check.ps1 -Exe <bin\Release\AntiDupl.NET.WinForms.exe> -s <new scratch folder>
param([string]$Exe, [string]$s)
. (Join-Path $PSScriptRoot 'ui_automation.ps1')
$gone = Join-Path $s 'listed'
New-Item -ItemType Directory -Force $gone | Out-Null
$failed = $true
try {
    $p = Start-Process -FilePath $Exe -ArgumentList '-s', "`"$s`"", '-search', "`"$gone`"" -PassThru
    $script:AdStarted.Add($p)
    Start-Sleep -Seconds 6
    $main = @($AE::RootElement.FindAll($TS::Children, (New-AdCondition $AE::ProcessIdProperty $p.Id))) |
        Where-Object { $_.FindFirst($TS::Children, (New-AdCondition $AE::ControlTypeProperty $CT::ToolBar)) } | Select-Object -First 1
    $toolbar = $main.FindFirst($TS::Children, (New-AdCondition $AE::ControlTypeProperty $CT::ToolBar))
    Send-AdClick @($toolbar.FindAll($TS::Children, (New-AdCondition $AE::ControlTypeProperty $CT::Button)))[4] $toolbar
    Start-Sleep -Seconds 2
    $isWindow = New-AdCondition $AE::ControlTypeProperty $CT::Window
    $form = @($main.FindAll($TS::Children, $isWindow)) | Select-Object -First 1
    [IO.Directory]::Delete($gone)
    Send-AdButton $form 'Add Folder'
    $picker = $null
    # Not the desktop's windows: one window not responding there makes
    # each walk over them take seconds.
    foreach ($i in 1..16) {
        Start-Sleep -Milliseconds 500
        $picker = @($form.FindAll($TS::Children, $isWindow)) + @($main.FindAll($TS::Children, $isWindow)) |
            Where-Object { $_.Current.ClassName -eq '#32770' } | Select-Object -First 1
        if ($picker) { break }
    }
    if (-not $picker) { throw 'no folder dialog' }
    $items = @($picker.FindAll($TS::Descendants, (New-AdCondition $AE::ControlTypeProperty $CT::ListItem)))
    $chosen = $items[0].Current.Name, $items[1].Current.Name
    $items[0].GetCurrentPattern([Windows.Automation.SelectionItemPattern]::Pattern).Select()
    $items[1].GetCurrentPattern([Windows.Automation.SelectionItemPattern]::Pattern).AddToSelection()
    Start-Sleep -Milliseconds 700
    # The dialog's own button: AutomationId 1 alone also finds a list item.
    $ok = @($picker.FindAll($TS::Children, [Windows.Automation.Condition]::TrueCondition)) |
        Where-Object { $_.Current.ClassName -eq 'Button' -and $_.Current.AutomationId -eq '1' } | Select-Object -First 1
    [AdUiNative]::PostMessage([IntPtr]$ok.Current.NativeWindowHandle, 0x00F5, [IntPtr]0, [IntPtr]0) | Out-Null
    Start-Sleep -Seconds 3
    $names = @($form.FindAll($TS::Descendants, (New-AdCondition $AE::ControlTypeProperty $CT::CheckBox))) | ForEach-Object { $_.Current.Name }
    $missing = @($chosen | Where-Object { $name = $_; -not ($names | Where-Object { (Split-Path -Leaf $_) -eq $name }) })
    $failed = $missing.Count -gt 0
    if ($failed) { "FAIL not listed: $($missing -join ', ')" } else { "PASS both listed: $($chosen -join ', ')" }
    Send-AdButton $form 'Cancel'
    Start-Sleep -Seconds 1
} finally { Stop-AdStrays }
if ($failed) { exit 1 }
