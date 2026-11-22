# The Options dialog's whole-number boxes (LabeledIntegerEdit), on Advanced
# -> RAM limit for Butteraugli's images, MB: the text is checked when focus
# leaves the box, not on every key. Emptied or invalid text stays while the
# box has focus; on leaving, a valid number written with group separators
# (16,384 / 16.384) is rewritten plainly, and an invalid or out-of-range one
# gives way to the last valid value. OK saves the value. Prints ok/FAIL per
# check and PASS or FAIL at the end.
#   pwsh -File ui_integer_edit_check.ps1 -Exe <bin\Release\AntiDupl.NET.WinForms.exe> -s <new scratch folder>
param([string]$Exe, [string]$s, [string]$Label = "RAM limit for Butteraugli's images, MB")
. (Join-Path $PSScriptRoot 'ui_automation.ps1')
$script:failures = 0
function Check([string]$what, [string]$got, [string]$expected) {
    $ok = $got -eq $expected
    if (-not $ok) { $script:failures++ }
    "$(if ($ok) { 'ok  ' } else { 'FAIL' }) ${what}: '$got'$(if (-not $ok) { ", expected '$expected'" })"
}
function Edit-Of($dialog, [string]$Label) {
    # The box's panel carries its label's name; the box itself is named
    # after the label of the row above it, so a search by name finds the
    # wrong box.
    $panel = $dialog.FindFirst($TS::Descendants, (New-Object Windows.Automation.AndCondition(
        (New-AdCondition $AE::NameProperty $Label), (New-AdCondition $AE::ControlTypeProperty $CT::Pane))))
    if (-not $panel) { throw "no panel '$Label'" }
    $panel.FindFirst($TS::Descendants, (New-AdCondition $AE::ControlTypeProperty $CT::Edit))
}
function Set-Text($edit, [string]$text) {
    $edit.SetFocus()
    $edit.GetCurrentPattern([Windows.Automation.ValuePattern]::Pattern).SetValue($text)
    Start-Sleep -Milliseconds 300
}
function Get-Text($edit) { $edit.GetCurrentPattern([Windows.Automation.ValuePattern]::Pattern).Current.Value }

try {
    $p, $main = Start-AdBuild $Exe $s
    Expand-AdWindow $main
    $dialog = Open-AdOptions $p $main
    $tab = $dialog.FindFirst($TS::Descendants, (New-Object Windows.Automation.AndCondition(
        (New-AdCondition $AE::NameProperty 'Advanced'), (New-AdCondition $AE::ControlTypeProperty $CT::TabItem))))
    $tab.GetCurrentPattern([Windows.Automation.SelectionItemPattern]::Pattern).Select()
    Start-Sleep -Milliseconds 700
    $edit = Edit-Of $dialog $Label
    $other = Edit-Of $dialog 'Maximal count of results'
    Check 'starts at the default' (Get-Text $edit) '512'

    Set-Text $edit ''
    Check 'emptied, while focused' (Get-Text $edit) ''
    Set-Text $edit '16.384'
    Check 'pasted with a dot, while focused' (Get-Text $edit) '16.384'
    $other.SetFocus(); Start-Sleep -Milliseconds 300
    Check 'after leaving: written plainly' (Get-Text $edit) '16384'

    Set-Text $edit 'abc'
    Check 'letters, while focused' (Get-Text $edit) 'abc'
    $other.SetFocus(); Start-Sleep -Milliseconds 300
    Check 'after leaving: the last valid value' (Get-Text $edit) '16384'

    Set-Text $edit '100000'
    $other.SetFocus(); Start-Sleep -Milliseconds 300
    Check 'out of range, after leaving: the last valid value' (Get-Text $edit) '16384'

    Set-Text $edit '24,576'
    $other.SetFocus(); Start-Sleep -Milliseconds 300
    Check 'pasted with a comma, after leaving' (Get-Text $edit) '24576'

    Send-AdButton $dialog 'OK'
    Start-Sleep -Seconds 1
    Stop-AdBuild $p $main
    $profile = Get-ChildItem -LiteralPath $s -Recurse -Filter default.xml | Select-Object -First 1
    $x = [xml](Get-Content -LiteralPath $profile.FullName -Raw)
    Check 'saved' $x.SelectSingleNode('//butteraugliCacheSize').InnerText '24576'
} catch { $script:failures++; "FAIL stopped: $_" } finally { Stop-AdStrays }
if ($script:failures) { "FAIL ($($script:failures))" } else { 'PASS' }
