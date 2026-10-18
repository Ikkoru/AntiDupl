# T12's check in the running program. Options dialog: choose Butteraugli,
# read its threshold list and working sizes, change the size and watch the
# default threshold follow, picture the dialog, OK. Then the saved profile,
# and after a restart the tool bar's lists.
#   pwsh -File ui_butteraugli_check.ps1 -Exe <bin\Release\AntiDupl.NET.WinForms.exe> -s <new scratch folder> -Shot <png>
# Expected: thresholds 8.5 / 6 / 9.5 / 5 for 768 / 512 / 1024 / 384 px,
# 37 thresholds from 0 to 50 without a unit, the profile saving
# Butteraugli / 9.5 / 1024, and the tool bar showing them after a restart.
param([string]$Exe, [string]$s, [string]$Shot)
. (Join-Path $PSScriptRoot 'ui_automation.ps1')

$p, $main = Start-AdBuild $Exe $s
$dialog = Open-AdOptions $p $main
$algorithm = $null; $threshold = $null; $size = $null
foreach ($c in Get-AdLists $dialog) {
    $names = Get-AdListItems $c
    if ($names -contains 'SSIM') { $algorithm = $c }
    elseif ($names -contains '768 px') { $size = $c }
    elseif (($names -contains '1 %') -and -not $threshold) { $threshold = $c }
}
"algorithms: $((Get-AdListItems $algorithm) -join ' | ')"
"start: $(Get-AdListValue $algorithm), threshold $(Get-AdListValue $threshold), size $(Get-AdListValue $size), size list enabled $($size.Current.IsEnabled)"
Select-AdListItem $algorithm 'Perceptual (Butteraugli)'
$t = Get-AdListItems $threshold
"chose Butteraugli -> threshold $(Get-AdListValue $threshold), $($t.Count) items: $($t[0..4] -join ' | ') ... $($t[-3..-1] -join ' | '); size list enabled $($size.Current.IsEnabled)"
foreach ($n in '512 px', '1024 px', '384 px', '768 px') {
    Select-AdListItem $size $n
    "chose $n -> threshold $(Get-AdListValue $threshold)"
}
Select-AdListItem $threshold '7.5'
Select-AdListItem $size '1024 px'
"chose 7.5, then 1024 px -> threshold $(Get-AdListValue $threshold)"
if ($Shot) { Save-AdWindowPicture $dialog $Shot }
Send-AdButton $dialog 'OK'
Start-Sleep -Seconds 2
Stop-AdBuild $p $main
"saved: $(Read-AdProfile $s | Out-String)".Trim()

$p, $main = Start-AdBuild $Exe $s
$lists = Get-AdLists $main
$tbAlgorithm = $lists | Where-Object { (Get-AdListItems $_) -contains 'SSIM' } | Select-Object -First 1
$tbThreshold = $lists | Where-Object { $_ -ne $tbAlgorithm } | Select-Object -First 1
"tool bar after restart: $($tbAlgorithm.Current.Name), threshold '$($tbThreshold.Current.Name)'"
Select-AdListItem $tbAlgorithm 'Local colour difference'
"tool bar: chose local colour -> threshold '$($tbThreshold.Current.Name)'"
Select-AdListItem $tbAlgorithm 'Perceptual (Butteraugli)'
"tool bar: chose Butteraugli -> threshold '$($tbThreshold.Current.Name)'"
Stop-AdBuild $p $main
