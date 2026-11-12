# The two thresholds shown beside the Options dialog's threshold list: only
# for the Butteraugli algorithms, following the working size, and inside the
# tab in English, Russian and German, its colour between that of text and of
# an unavailable option. Prints ok/FAIL per check and PASS or FAIL at the end;
# with -Shot, a picture of the dialog in each language, a Butteraugli
# algorithm chosen, named <Shot>-<language>.png. -ColorMode Dark for the dark
# theme (Classic is the light one).
#   pwsh -File ui_threshold_hint_check.ps1 -Exe <bin\Release\AntiDupl.NET.WinForms.exe> -s <new scratch folder>
param([string]$Exe, [string]$s, [string]$Shot, [string]$ColorMode = 'Classic')
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

# How far a text's strongest pixel stands from its background, on a picture
# of the dialog: anti-aliasing keeps most of a thin text's pixels off its
# colour, but the order of three texts of one size holds.
function Get-Contrast($bitmap, $window, $rect) {
    $x0 = [int]($rect.Left - $window.Left); $y0 = [int]($rect.Top - $window.Top)
    function Luma($c) { 0.299 * $c.R + 0.587 * $c.G + 0.114 * $c.B }
    $background = Luma $bitmap.GetPixel($x0, $y0)
    $most = 0
    for ($y = $y0; $y -lt $y0 + $rect.Height; $y++) {
        for ($x = $x0; $x -lt $x0 + $rect.Width; $x++) {
            $d = [math]::Abs((Luma $bitmap.GetPixel($x, $y)) - $background)
            if ($d -gt $most) { $most = $d }
        }
    }
    [int]$most
}

# With a Butteraugli algorithm chosen, the shifted search's box is unavailable.
function Check-Colour([string]$language, $dialog, $hint, $boxes, $tab) {
    $picture = Join-Path $s 'colours.png'
    Save-AdWindowPicture $dialog $picture
    $bitmap = New-Object System.Drawing.Bitmap $picture
    $window = $dialog.Current.BoundingRectangle
    $h = $hint.Current.BoundingRectangle
    $label = @($dialog.FindAll($TS::Descendants, (New-AdCondition $AE::ControlTypeProperty $CT::Text))) | Where-Object {
        $r = $_.Current.BoundingRectangle
        [math]::Abs($r.Top - $h.Top) -lt 5 -and $r.Right -le $h.Left + 1 -and $r.Left -gt $tab.Left + 70 } | Select-Object -First 1
    $unavailable = $boxes | Where-Object { -not $_.Current.IsEnabled } | Select-Object -First 1
    $u = $unavailable.Current.BoundingRectangle
    $u = New-Object Windows.Rect ($u.Left + 20), $u.Top, ($u.Width - 20), $u.Height
    $normal = Get-Contrast $bitmap $window $label.Current.BoundingRectangle
    $remark = Get-Contrast $bitmap $window $h
    $grey = Get-Contrast $bitmap $window $u
    $bitmap.Dispose()
    Check "$language, colour: text $normal, hint $remark, unavailable $grey" ($normal -gt $remark -and $remark -gt $grey) 'True'
}

$languages = [ordered]@{
    English = @{ Title = 'Options'; Cancel = 'Cancel'; Other = 'Mean square difference', 'SSIM', 'Local colour difference'
                 Butteraugli = 'Perceptual (Butteraugli)'; Aligned = 'Aligned perceptual (crops, shifts)' }
    Russian = @{ Title = 'Опции'; Cancel = 'Отмена'; Other = 'Среднеквадратичная разность', 'SSIM', 'Локальная разность цвета'
                 Butteraugli = 'Перцептивная (Butteraugli)'; Aligned = 'Перцептивная с выравниванием (обрезка, сдвиг)' }
    # The widest threshold label, beside the English hint: a language file
    # without the hint's text falls back to it.
    German = @{ Title = 'Optionen'; Cancel = 'Abbrechen'; Other = 'Differenz', 'SSIM', 'Local colour difference'
                Butteraugli = 'Perceptual (Butteraugli)'; Aligned = 'Aligned perceptual (crops, shifts)' }
}
$expected = [ordered]@{ '384 px' = '7.5 and 11'; '512 px' = '9 and 13'; '1024 px' = '13 and 16'; '768 px' = '12 and 15' }

try {
    # A first start writes the options file the settings below go in.
    $file = Join-Path $s 'options.xml'
    if (-not (Test-Path -LiteralPath $file)) {
        $p, $main = Start-AdBuild $Exe $s
        Stop-AdBuild $p $main
    }
    foreach ($language in $languages.Keys) {
        $l = $languages[$language]
        $x = [IO.File]::ReadAllText($file) -replace '<Language>[^<]*</Language>', "<Language>$language</Language>"
        [IO.File]::WriteAllText($file, ($x -replace '<colorMode>[^<]*</colorMode>', "<colorMode>$ColorMode</colorMode>"))
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
        # A build may lack the aligned search, but not in one language only:
        # a renamed entry would otherwise be skipped without a word.
        if ($language -eq 'English') { $script:aligned = $offered -contains $l.Aligned }
        Check "$language, aligned search offered as in English" ($offered -contains $l.Aligned) $script:aligned
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
                Check-Colour $language $dialog $hint $boxes $tab
            }
        }
        if ($Shot) { Save-AdWindowPicture $dialog "$Shot-$language.png" }
        Send-AdButton $dialog $l.Cancel
        Start-Sleep -Seconds 1
        Stop-AdBuild $p $main
    }
} finally { Stop-AdStrays }
"$(if ($script:failures) { "FAIL: $script:failures" } else { 'PASS' })"
