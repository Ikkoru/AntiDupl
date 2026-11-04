# The two thresholds shown beside the Options dialog's threshold list: only
# for the Butteraugli algorithms, following the working size, and inside the
# tab in English, Russian and German. Prints ok/FAIL per check and PASS or
# FAIL at the end; with -Shot, a picture of the dialog in each language, a
# Butteraugli algorithm chosen, named <Shot>-<language>.png.
#   pwsh -File ui_threshold_hint_check.ps1 -Exe <bin\Release\AntiDupl.NET.WinForms.exe> -s <new scratch folder>
param([string]$Exe, [string]$s, [string]$Shot)
. (Join-Path $PSScriptRoot 'ui_automation.ps1')
$script:failures = 0
function Check([string]$what, [string]$got, [string]$expected) {
    $ok = $got -eq $expected
    if (-not $ok) { $script:failures++ }
    "$(if ($ok) { 'ok  ' } else { 'FAIL' }) ${what}: '$got'$(if (-not $ok) { ", expected '$expected'" })"
}

# The hint is the one text of the dialog holding two numbers, right of the
# lists: the next list takes its name from the label before it, a hidden one
# too, so that name alone says nothing.
function Get-Hint($dialog) {
    $tab = $dialog.FindFirst($TS::Descendants, (New-AdCondition $AE::ControlTypeProperty $CT::Tab)).Current.BoundingRectangle
    @($dialog.FindAll($TS::Descendants, (New-AdCondition $AE::ControlTypeProperty $CT::Text))) |
        Where-Object { $_.Current.Name -match '^\D*\d+([.,]\d+)?\D+\d+' -and $_.Current.BoundingRectangle.Left -gt $tab.Left + 100 } |
        Select-Object -First 1
}
function Get-HintValues($dialog) {
    $hint = Get-Hint $dialog
    if (-not $hint) { return 'none' }
    (([regex]::Matches($hint.Current.Name, '\d+([.,]\d+)?') | ForEach-Object { $_.Value -replace ',', '.' }) -join ' and ')
}

$languages = [ordered]@{
    English = @{ Title = 'Options'; Cancel = 'Cancel'; Other = 'Mean square difference', 'SSIM', 'Local colour difference'
                 Butteraugli = 'Perceptual (Butteraugli)'; Aligned = 'Aligned perceptual (crops, shifts)' }
    Russian = @{ Title = 'Опции'; Cancel = 'Отмена'; Other = 'Среднеквадратичная разность', 'SSIM', 'Локальная разность цвета'
                 Butteraugli = 'Перцептивная (Butteraugli)'; Aligned = 'Перцептивная с выравниванием (кадрирование, сдвиг)' }
    # The widest threshold label, beside the English hint: a language file
    # without the hint's text falls back to it.
    German = @{ Title = 'Optionen'; Cancel = 'Abbrechen'; Other = 'Differenz', 'SSIM', 'Local colour difference'
                Butteraugli = 'Perceptual (Butteraugli)'; Aligned = 'Aligned perceptual (crops, shifts)' }
}
$expected = [ordered]@{ '384 px' = '5 and 12'; '512 px' = '6 and 14'; '1024 px' = '9.5 and 16'; '768 px' = '8.5 and 15' }

try {
    foreach ($language in $languages.Keys) {
        $l = $languages[$language]
        $file = Join-Path $s 'options.xml'
        if (Test-Path -LiteralPath $file) {
            $x = [IO.File]::ReadAllText($file) -replace '<Language>[^<]*</Language>', "<Language>$language</Language>"
            [IO.File]::WriteAllText($file, $x)
        } elseif ($language -ne 'English') { throw "no options.xml to set the language in" }
        $p, $main = Start-AdBuild $Exe $s
        $dialog = Open-AdOptions $p $main -Title $l.Title
        $dAlgorithm = $null; $dSize = $null
        foreach ($c in Get-AdLists $dialog) {
            $names = Get-AdListItems $c
            if ($names -contains 'SSIM') { $dAlgorithm = $c; $offered = $names }
            elseif ($names -contains '768 px') { $dSize = $c }
        }
        foreach ($a in $l.Other) {
            Select-AdListItem $dAlgorithm $a
            Check "$language, $a" (Get-HintValues $dialog) 'none'
        }
        $withHint = @($l.Butteraugli) + @($l.Aligned | Where-Object { $offered -contains $_ })
        foreach ($a in $withHint) {
            Select-AdListItem $dAlgorithm $a
            foreach ($size in $expected.Keys) {
                Select-AdListItem $dSize $size
                Check "$language, $a, $size" (Get-HintValues $dialog) $expected[$size]
            }
            $hint = Get-Hint $dialog
            if ($hint) {
                # A panel's scroll bars aren't in UI Automation's tree, so what
                # overflows is read from the edges. 8: the tab page's own frame
                # and padding. A horizontal scroll bar takes the height of the
                # bottom check box too.
                $tab = $dialog.FindFirst($TS::Descendants, (New-AdCondition $AE::ControlTypeProperty $CT::Tab)).Current.BoundingRectangle
                $boxes = @($dialog.FindAll($TS::Descendants, (New-AdCondition $AE::ControlTypeProperty $CT::CheckBox)))
                Check "$language, inside the tab ('$($hint.Current.Name)')" ($hint.Current.BoundingRectangle.Right -le $tab.Right - 8) 'True'
                Check "$language, last check box inside the tab" ($boxes[-1].Current.BoundingRectangle.Bottom -le $tab.Bottom - 8) 'True'
            }
        }
        if ($Shot) { Save-AdWindowPicture $dialog "$Shot-$language.png" }
        Send-AdButton $dialog $l.Cancel
        Start-Sleep -Seconds 1
        Stop-AdBuild $p $main
    }
} finally { Stop-AdStrays }
"$(if ($script:failures) { "FAIL: $script:failures" } else { 'PASS' })"
