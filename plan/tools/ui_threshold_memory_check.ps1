# Each algorithm keeps the threshold last used with it (and Butteraugli one
# per working size): switching away and back, in the tool bar and in the
# Options dialog, and after a restart. Prints ok/FAIL per check and PASS or
# FAIL at the end.
#   pwsh -File ui_threshold_memory_check.ps1 -Exe <bin\Release\AntiDupl.NET.WinForms.exe> -s <new scratch folder>
param([string]$Exe, [string]$s)
. (Join-Path $PSScriptRoot 'ui_automation.ps1')
$script:failures = 0
function Check([string]$what, [string]$got, [string]$expected) {
    $ok = $got -eq $expected
    if (-not $ok) { $script:failures++ }
    "$(if ($ok) { 'ok  ' } else { 'FAIL' }) ${what}: '$got'$(if (-not $ok) { ", expected '$expected'" })"
}
function ToolBarLists($main) {
    $lists = Get-AdLists $main
    $algorithm = $lists | Where-Object { (Get-AdListItems $_) -contains 'SSIM' } | Select-Object -First 1
    $threshold = $lists | Where-Object { $_ -ne $algorithm } | Select-Object -First 1
    return @($algorithm, $threshold)
}

try {
# --- tool bar: a threshold for each algorithm, then back to each
$p, $main = Start-AdBuild $Exe $s
$algorithm, $threshold = ToolBarLists $main
$choices = [ordered]@{ 'Mean square difference' = '3 %'; 'SSIM' = '0.5 %'; 'Local colour difference' = '2 %'; 'Perceptual (Butteraugli)' = '7.5' }
foreach ($a in $choices.Keys) {
    Select-AdListItem $algorithm $a
    Select-AdListItem $threshold $choices[$a]
}
foreach ($a in $choices.Keys) {
    Select-AdListItem $algorithm $a
    Check "tool bar, back to $a" $threshold.Current.Name $choices[$a]
}
Stop-AdBuild $p $main

# --- after a restart: the profile's algorithm and threshold, and the others remembered
$p, $main = Start-AdBuild $Exe $s
$algorithm, $threshold = ToolBarLists $main
Check 'after restart, threshold' $threshold.Current.Name '7.5'
Select-AdListItem $algorithm 'SSIM'
Check 'after restart, SSIM' $threshold.Current.Name '0.5 %'
Select-AdListItem $algorithm 'Perceptual (Butteraugli)'

# --- Options dialog: algorithms, then Butteraugli's working sizes
$dialog = Open-AdOptions $p $main
$dAlgorithm = $null; $dThreshold = $null; $dSize = $null
foreach ($c in Get-AdLists $dialog) {
    $names = Get-AdListItems $c
    if ($names -contains 'SSIM') { $dAlgorithm = $c }
    elseif ($names -contains '768 px') { $dSize = $c }
    elseif (($names -contains '1 %' -or $names -contains '1') -and -not $dThreshold) { $dThreshold = $c }
}
Check 'dialog opens with' (Get-AdListValue $dThreshold) '7.5'
Select-AdListItem $dAlgorithm 'Local colour difference'
Check 'dialog, local colour' (Get-AdListValue $dThreshold) '2 %'
Select-AdListItem $dAlgorithm 'Perceptual (Butteraugli)'
Check 'dialog, back to Butteraugli' (Get-AdListValue $dThreshold) '7.5'
Select-AdListItem $dSize '512 px'
Check 'dialog, 512 px first time (its default)' (Get-AdListValue $dThreshold) '6'
Select-AdListItem $dThreshold '5.5'
Select-AdListItem $dSize '768 px'
Check 'dialog, back to 768 px' (Get-AdListValue $dThreshold) '7.5'
Select-AdListItem $dSize '512 px'
Check 'dialog, back to 512 px' (Get-AdListValue $dThreshold) '5.5'
Send-AdButton $dialog 'Set default'
Start-Sleep -Seconds 1
Check 'dialog, Set default' "$(Get-AdListValue $dAlgorithm) / $(Get-AdListValue $dThreshold)" 'Mean square difference / 5 %'
Send-AdButton $dialog 'Cancel'
Start-Sleep -Seconds 1
Stop-AdBuild $p $main
} finally { Stop-AdStrays }

if ($script:failures) { "FAIL ($($script:failures))" } else { 'PASS' }
