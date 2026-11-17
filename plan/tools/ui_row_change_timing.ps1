# How long the results list takes to go from one row to the next, in a
# build's running program: for comparing builds when changing the selected
# row feels slower. Searches the folders with the build's own core
# (core_search.py), saves the results as the scratch folder's default
# profile, starts the build on it and presses Down, then Up, waiting after
# each key until the program is idle again (Process.WaitForInputIdle: the
# key handled, the preview loaded and everything repainted). Prints the
# median and mean milliseconds per row change, per view; -Raw also every
# time, -Highlight turns on the highlighted differences, -ColorMode Dark
# (Classic, System) sets the theme of builds that have one, and
# -Set "Name=value;..." any other element of options.xml.
# Compare builds on a list whose rows all cost the same (one picture copied
# several times): builds that sort differently put other pictures on the
# rows timed, and a picture's size alone moves a row change from tens to
# hundreds of milliseconds.
#   pwsh -File ui_row_change_timing.ps1 -Exe <bin\Release\AntiDupl.NET.WinForms.exe> -s <new scratch folder> -Folder "<images>[;<images>]" [-Steps 20] [-Threshold 5]
# Works with builds back to v2.3.13: nothing it uses is newer. Compare
# builds on the same folders, one after another, nothing else running.
param([string]$Exe, [string]$s, [string[]]$Folder, [int]$Steps = 20, [int]$Threshold = 5,
      [string[]]$Views = @('VerticalPairTable', 'HorizontalPairTable'), [switch]$Raw, [switch]$Highlight, [string]$ColorMode, [string]$Set)
. (Join-Path $PSScriptRoot 'ui_automation.ps1')
# pwsh -File passes "a,b" as one string: folders may also be given as "a;b".
$Folder = @($Folder | ForEach-Object { $_ -split '[;,]' } | Where-Object { $_ })

if (Test-Path -LiteralPath $s) { throw "give a folder that doesn't exist yet: $s" }
New-Item -ItemType Directory $s | Out-Null
$dll = Split-Path $Exe

function Set-Xml([string]$file, [hashtable]$values) {
    $x = [IO.File]::ReadAllText($file)
    foreach ($k in $values.Keys) {
        if ($x -cnotmatch "<$k>") { throw "no <$k> in $file" }
        $x = $x -creplace "<$k>[^<]*</$k>", "<$k>$($values[$k])</$k>"
    }
    [IO.File]::WriteAllText($file, $x)
}

# One key, then the time until the program has handled it and is waiting
# for input again.
function Measure-Key($p, [IntPtr]$h, [int]$vk) {
    $sw = [Diagnostics.Stopwatch]::StartNew()
    [AdUiNative]::PostMessage($h, 0x100, [IntPtr]$vk, [IntPtr]1) | Out-Null           # WM_KEYDOWN
    [AdUiNative]::PostMessage($h, 0x101, [IntPtr]$vk, [IntPtr]0xC0000001) | Out-Null  # WM_KEYUP
    if (-not $p.WaitForInputIdle(30000)) { throw "the program did not become idle" }
    $sw.Elapsed.TotalMilliseconds
}

function Lp([int]$x, [int]$y) { [IntPtr](($y -shl 16) -bor ($x -band 0xFFFF)) }

# A left click at a point of the list (client coordinates, packed by Lp).
function Measure-Click($p, [IntPtr]$h, [IntPtr]$lp) {
    $sw = [Diagnostics.Stopwatch]::StartNew()
    [AdUiNative]::PostMessage($h, 0x200, [IntPtr]0, $lp) | Out-Null   # WM_MOUSEMOVE
    [AdUiNative]::PostMessage($h, 0x201, [IntPtr]1, $lp) | Out-Null   # WM_LBUTTONDOWN
    [AdUiNative]::PostMessage($h, 0x202, [IntPtr]0, $lp) | Out-Null   # WM_LBUTTONUP
    if (-not $p.WaitForInputIdle(30000)) { throw "the program did not become idle" }
    $sw.Elapsed.TotalMilliseconds
}

function Write-Times([string]$what, $times) {
    $sorted = $times | Sort-Object
    "{0,-30} median {1,7:N1} ms  mean {2,7:N1} ms  max {3,7:N1} ms" -f $what,
        $sorted[[int]($sorted.Count / 2)], ($times | Measure-Object -Average).Average, $sorted[-1]
    if ($Raw) { "  " + (($times | ForEach-Object { '{0:N0}' -f $_ }) -join ' ') }
}

try {
    # A first start writes the settings folder's files.
    $p, $main = Start-AdBuild $Exe $s
    Stop-AdBuild $p $main
    $settings = Get-ChildItem -LiteralPath $s -Recurse -Filter default.xml | Select-Object -First 1
    if (-not $settings) { throw "no default.xml under $s" }
    $results = Join-Path $settings.DirectoryName 'default.adr'
    $user = Join-Path $s 'core-search'
    $out = & py -3 (Join-Path $PSScriptRoot 'core_search.py') $dll $user @Folder --threshold $Threshold --any-ratio --save-results $results
    if ($LASTEXITCODE) { throw "core_search failed" }
    $pairs = @($out | Where-Object { $_ -match '  shows ' }).Count
    "$pairs pairs; $Steps row changes down and $Steps up per view"
    if ($pairs -lt $Steps + 1) { throw "too few pairs for $Steps steps" }

    $options = Join-Path $s 'options.xml'
    foreach ($view in $Views) {
        Set-Xml $options @{ viewMode = $view; HighlightDifference = "$([bool]$Highlight)".ToLower() }
        # Builds without a dark mode have no colorMode.
        if ($ColorMode) { Set-Xml $options @{ colorMode = $ColorMode } }
        foreach ($pair in ($Set -split ';' | Where-Object { $_ })) {
            $k, $v = $pair -split '=', 2
            Set-Xml $options @{ $k = $v }
        }
        $p, $main = Start-AdBuild $Exe $s
        Expand-AdWindow $main
        Start-Sleep -Seconds 2
        $grid = $main.FindFirst($TS::Descendants, (New-AdCondition $AE::ControlTypeProperty $CT::DataGrid))
        if (-not $grid) { $grid = $main.FindFirst($TS::Descendants, (New-AdCondition $AE::ControlTypeProperty $CT::Table)) }
        if (-not $grid) { throw "results list not found" }
        $h = [IntPtr]$grid.Current.NativeWindowHandle
        $grid.SetFocus()
        $p.WaitForInputIdle(30000) | Out-Null
        # A first move loads what the first preview didn't (fonts, decoders).
        Measure-Key $p $h 0x28 | Out-Null
        Measure-Key $p $h 0x26 | Out-Null
        $times = @(1..$Steps | ForEach-Object { Measure-Key $p $h 0x28 }) + @(1..$Steps | ForEach-Object { Measure-Key $p $h 0x26 })
        Write-Times "$view, keys" $times
        # Clicks on the second and the fourth visible row, by turns, as a
        # user picks rows with the mouse.
        $rows = @($grid.FindAll($TS::Children, [Windows.Automation.Condition]::TrueCondition) |
            Where-Object { $_.Current.BoundingRectangle.Height -gt 0 -and $_.Current.ControlType -ne $CT::Header -and $_.Current.Name -notmatch 'Top Row|Header' })
        if ($rows.Count -ge 5) {
            $g = $grid.Current.BoundingRectangle
            $at = @($rows[2], $rows[4]) | ForEach-Object {
                $r = $_.Current.BoundingRectangle
                Lp ([int]($r.X - $g.X + [Math]::Min(60, $r.Width / 2))) ([int]($r.Y - $g.Y + $r.Height / 2))
            }
            $times = @(1..(2 * $Steps) | ForEach-Object { Measure-Click $p $h $at[$_ % 2] })
            Write-Times "$view, clicks" $times
        } else { "$view, clicks: rows not found ($($rows.Count))" }
        Stop-AdBuild $p $main
    }
} finally { Stop-AdStrays }
