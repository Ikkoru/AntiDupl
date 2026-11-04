# Checks the aligned search in the running program, in a new scratch
# settings folder (PowerShell 7). -Search holds a picture and a crop or shifted
# copy of it, and nothing else. (1) The tool bar offers the algorithm, with
# Butteraugli's thresholds and default; (2) the Options dialog shows the same
# and enables the working size; (3) the profile keeps it; (4) plain Butteraugli
# finds no pair in the folder; (5) the aligned search does, under the default
# threshold. With -Shot, a picture of the window with the pair showing, the
# highlighting on with Ignore compression noise: the crop should show no marks.
# Prints one line per check, PASS or FAIL.
#   ui_aligned_check.ps1 -Exe <exe> -s <new scratch folder> -Search <folder> [-Shot <png>]
param([string]$Exe, [string]$s, [string]$Search, [string]$Shot)
. (Join-Path $PSScriptRoot 'ui_automation.ps1')
$Name = 'Aligned perceptual (crops, shifts)'
function Show-Check([bool]$ok, [string]$text) { '{0} {1}' -f $(if ($ok) { 'PASS' } else { 'FAIL' }), $text }

# Runs a search from the command line and returns its log line.
function Invoke-AdSearch([string]$Exe, [string]$s, [string]$Search, [switch]$KeepOpen) {
    $log = Join-Path $s 'decisions.jsonl'
    $before = @(Get-Content -LiteralPath $log -Encoding utf8 | Where-Object { $_ -match '"event":"search"' }).Count
    $p = Start-Process -FilePath $Exe -ArgumentList '-s', "`"$s`"", '-search', "`"$Search`"", '-start' -PassThru
    $script:AdStarted.Add($p)
    for ($i = 0; $i -lt 120; $i++) {
        Start-Sleep -Seconds 1
        $lines = @(Get-Content -LiteralPath $log -Encoding utf8 | Where-Object { $_ -match '"event":"search"' })
        if ($lines.Count -gt $before) { break }
    }
    if ($lines.Count -le $before) { throw 'the search did not finish' }
    Start-Sleep -Seconds 3
    $byPid = New-AdCondition $AE::ProcessIdProperty $p.Id
    $main = $null
    for ($i = 0; $i -lt 30 -and -not $main; $i++) {
        try {
            $main = @($AE::RootElement.FindAll($TS::Children, $byPid)) | Where-Object { $_.FindFirst($TS::Children, (New-AdCondition $AE::ControlTypeProperty $CT::ToolBar)) } | Select-Object -First 1
        } catch { Start-Sleep -Seconds 1 }
    }
    return @($p, $main, ($lines[-1] | ConvertFrom-Json))
}

try {
    $p, $main = Start-AdBuild $Exe $s
    $lists = Get-AdLists $main
    $algorithm = $lists | Where-Object { (Get-AdListItems $_) -contains 'SSIM' } | Select-Object -First 1
    $threshold = $lists | Where-Object { $_ -ne $algorithm } | Select-Object -First 1
    $offered = (Get-AdListItems $algorithm) -contains $Name
    Show-Check $offered "(1) the tool bar offers '$Name'"
    Select-AdListItem $algorithm $Name
    Show-Check ($threshold.Current.Name -eq '8.5') "(1) its threshold on the tool bar: '$($threshold.Current.Name)'"

    $dialog = Open-AdOptions $p $main
    $dAlgorithm = $null; $dThreshold = $null; $dSize = $null
    foreach ($c in Get-AdLists $dialog) {
        $names = Get-AdListItems $c
        if ($names -contains 'SSIM') { $dAlgorithm = $c }
        elseif ($names -contains '768 px') { $dSize = $c }
        elseif (($names -contains '8.5') -and -not $dThreshold) { $dThreshold = $c }
    }
    Show-Check ((Get-AdListValue $dAlgorithm) -eq $Name -and (Get-AdListValue $dThreshold) -eq '8.5' -and $dSize.Current.IsEnabled) `
        "(2) Options: '$(Get-AdListValue $dAlgorithm)', threshold $(Get-AdListValue $dThreshold), size list enabled $($dSize.Current.IsEnabled)"
    Select-AdListItem $dSize '1024 px'
    Show-Check ((Get-AdListValue $dThreshold) -eq '9.5') "(2) at 1024 px the default follows: $(Get-AdListValue $dThreshold)"
    Select-AdListItem $dSize '768 px'
    Send-AdButton $dialog 'OK'
    Start-Sleep -Seconds 2
    Stop-AdBuild $p $main
    $saved = Read-AdProfile $s
    Show-Check ($saved.algorithmComparing -eq 'ButteraugliAligned') "(3) saved: $($saved.algorithmComparing) $($saved.thresholdDifference)"

    # The highlighting for the picture; both copies of each setting.
    $optionsFile = Join-Path $s 'options.xml'
    $x = [xml](Get-Content -LiteralPath $optionsFile -Raw -Encoding utf8)
    foreach ($name in 'HighlightDifference', 'IgnoreCompressionNoise') { $x.SelectSingleNode("//resultsOptions/$name").InnerText = 'true' }
    $x.Save($optionsFile)
    $profile = Get-ChildItem -LiteralPath $s -Recurse -Filter default.xml | Select-Object -First 1
    function Set-AdAlgorithm([string]$value) {
        $x = [xml](Get-Content -LiteralPath $profile.FullName -Raw -Encoding utf8)
        foreach ($name in 'algorithmComparing', 'AlgorithmComparing') { $x.SelectSingleNode("//compareOptions/$name").InnerText = $value }
        foreach ($name in 'ratioControl', 'RatioControl') { $x.SelectSingleNode("//compareOptions/$name").InnerText = 'false' }
        $x.Save($profile.FullName)
    }

    Set-AdAlgorithm 'Butteraugli'
    $p, $main, $event = Invoke-AdSearch $Exe $s $Search
    Show-Check ($event.settings.algorithm -eq 'Butteraugli' -and $event.pairs -eq 0) "(4) plain Butteraugli: $($event.pairs) pairs of $($event.images) images"
    Stop-AdBuild $p $main

    Set-AdAlgorithm 'ButteraugliAligned'
    $p, $main, $event = Invoke-AdSearch $Exe $s $Search
    Show-Check ($event.settings.algorithm -eq 'ButteraugliAligned' -and $event.pairs -ge 1) "(5) aligned: $($event.pairs) pairs of $($event.images) images"
    $result = Get-Content -LiteralPath (Join-Path $s 'decisions.jsonl') -Encoding utf8 | Where-Object { $_ -match '"event":"result"' } | Select-Object -Last 1 | ConvertFrom-Json
    Show-Check ($result.difference -le 8.5 -and $result.difference -gt 0) "(5) its difference: $($result.difference)"
    if ($Shot) {
        Start-Sleep -Seconds 4
        Save-AdWindowPicture $main $Shot
    }
    Stop-AdBuild $p $main
} finally { Stop-AdStrays }
