# Checks the aligned search's level setting and its memory warning in the
# running program, in a new scratch settings folder (PowerShell 7). -Many is
# a folder of so many pictures that the highest level's keypoints don't fit
# in the free memory (many_images.py beside it makes one): the highest
# level counts about 0.4 MB a picture against what is free, less a tenth of
# all the memory (1 GB at least) and half a GB. (1) Options > Advanced offers the level
# list, disabled but for the aligned search; (2) the profile keeps the level
# chosen; (3) with the highest level set, a search of -Many shows the
# warning as it starts, while it runs, with the text for a level kept
# though it doesn't fit; its Stop button stops the search, and the warning
# stays once the search has ended, its Stop button off; (4) with Auto, the
# warning says the search looks for larger crops instead. -Shots names a
# folder for pictures of the dialog and of each warning.
# Prints one line per check, PASS or FAIL.
#   ui_aligned_level_check.ps1 -Exe <exe> -s <new scratch folder> -Many <folder> [-Shots <folder>]
param([string]$Exe, [string]$s, [string]$Many, [string]$Shots)
. (Join-Path $PSScriptRoot 'ui_automation.ps1')
$Aligned = 'Aligned perceptual (crops, shifts)'
$Auto = 'Auto: as small as memory allows'
$Highest = '1/50 of image, 4 GB per 10k files'
$WarningTitle = 'Not enough memory for the smallest crops'
function Show-Check([bool]$ok, [string]$text) { '{0} {1}' -f $(if ($ok) { 'PASS' } else { 'FAIL' }), $text }

# Sets the profile's aligned level (both copies the profile keeps).
function Set-AdLevel([int]$level) {
    $profile = Get-ChildItem -LiteralPath $s -Recurse -Filter default.xml | Select-Object -First 1
    $x = [xml](Get-Content -LiteralPath $profile.FullName -Raw -Encoding utf8)
    foreach ($name in 'alignedLevel', 'AlignedLevel') { $x.SelectSingleNode("//compareOptions/$name").InnerText = "$level" }
    $x.Save($profile.FullName)
}

# Starts a search of -Many from the command line and waits for the warning.
# Returns @(process, warning window or null).
function Start-AdManySearch() {
    $p = Start-Process -FilePath $Exe -ArgumentList '-s', "`"$s`"", '-search', "`"$Many`"", '-start' -PassThru
    $script:AdStarted.Add($p)
    $byPid = New-AdCondition $AE::ProcessIdProperty $p.Id
    $isWindow = New-AdCondition $AE::ControlTypeProperty $CT::Window
    for ($i = 0; $i -lt 180; $i++) {
        Start-Sleep -Seconds 1
        try {
            foreach ($top in @($AE::RootElement.FindAll($TS::Children, $byPid))) {
                if ($top.Current.Name -eq $WarningTitle) { return @($p, $top) }
                $inner = @($top.FindAll($TS::Children, $isWindow)) | Where-Object { $_.Current.Name -eq $WarningTitle } | Select-Object -First 1
                if ($inner) { return @($p, $inner) }
            }
        } catch {}
    }
    return @($p, $null)
}

function Get-AdWarningText($warning) {
    (@($warning.FindAll($TS::Descendants, (New-AdCondition $AE::ControlTypeProperty $CT::Text))) | ForEach-Object { $_.Current.Name }) -join ' '
}

function Get-AdWarningButton($warning, [string]$name) {
    $warning.FindFirst($TS::Descendants, (New-Object Windows.Automation.AndCondition(
        (New-AdCondition $AE::NameProperty $name), (New-AdCondition $AE::ControlTypeProperty $CT::Button))))
}

# The search's progress window, while the search runs.
function Test-AdSearching($p) {
    # The progress window's title starts so while the search runs; a window
    # closing as it is read makes UI Automation throw, and is read again.
    # It is a window of its own or one inside the main window, as dialogs
    # owned by it are in UI Automation's tree.
    $byPid = New-AdCondition $AE::ProcessIdProperty $p.Id
    $isWindow = New-AdCondition $AE::ControlTypeProperty $CT::Window
    for ($try = 0; $try -lt 5; $try++) {
        try {
            $names = @()
            foreach ($top in @($AE::RootElement.FindAll($TS::Children, $byPid))) {
                $names += $top.Current.Name
                $names += @($top.FindAll($TS::Children, $isWindow) | ForEach-Object { $_.Current.Name })
            }
            $script:AdWindowNames = $names -join ' | '
            return [bool]($names | Where-Object { $_ -like 'Search*' -or $_ -like 'Stopping*' -or $_ -like 'Result processing*' })
        } catch { Start-Sleep -Milliseconds 300 }
    }
    $true
}

# The main window of a build started from the command line.
function Get-AdMain($p) {
    $byPid = New-AdCondition $AE::ProcessIdProperty $p.Id
    @($AE::RootElement.FindAll($TS::Children, $byPid)) |
        Where-Object { $_.FindFirst($TS::Children, (New-AdCondition $AE::ControlTypeProperty $CT::ToolBar)) } | Select-Object -First 1
}

# One search of -Many: the warning's text, Stop, and the warning after.
function Test-AdWarning([string]$label, [string]$expected) {
    $p, $warning = Start-AdManySearch
    Show-Check ([bool]$warning) "($label) the warning shows as the search starts"
    if (-not $warning) { Stop-Process -Id $p.Id; return }
    $text = Get-AdWarningText $warning
    "  $text"
    Show-Check ($text -like "*$expected*") "($label) it says: '$expected'"
    if ($Shots) { Save-AdWindowPicture $warning (Join-Path $Shots "warning-$label.png") }
    $running = Test-AdSearching $p
    Show-Check $running "($label) the search runs meanwhile"
    if (-not $running) { "  windows: $script:AdWindowNames"; Stop-Process -Id $p.Id; return }
    $stop = Get-AdWarningButton $warning 'Stop search'
    [AdUiNative]::PostMessage([IntPtr]$stop.Current.NativeWindowHandle, 0x00F5, [IntPtr]0, [IntPtr]0) | Out-Null
    $ended = $false
    for ($i = 0; $i -lt 120 -and -not $ended; $i++) { Start-Sleep -Seconds 1; $ended = -not (Test-AdSearching $p) }
    Show-Check $ended "($label) its Stop button stops the search"
    Start-Sleep -Seconds 2
    $still = $false; $stopOff = $false
    try { $still = $warning.Current.Name -eq $WarningTitle; $stopOff = -not (Get-AdWarningButton $warning 'Stop search').Current.IsEnabled } catch {}
    Show-Check ($still -and $stopOff) "($label) the warning stays once the search has ended, its Stop button off"
    $close = Get-AdWarningButton $warning 'Close'
    [AdUiNative]::PostMessage([IntPtr]$close.Current.NativeWindowHandle, 0x00F5, [IntPtr]0, [IntPtr]0) | Out-Null
    Start-Sleep -Seconds 1
    $main = Get-AdMain $p
    if ($main) { Stop-AdBuild $p $main } else { Stop-Process -Id $p.Id }
}

try {
    New-Item -ItemType Directory -Force -Path $s | Out-Null
    if ($Shots) { New-Item -ItemType Directory -Force -Path $Shots | Out-Null }
    $p, $main = Start-AdBuild $Exe $s
    Expand-AdWindow $main
    $dialog = Open-AdOptions $p $main
    # A tab's lists are there only while it shows.
    function Select-AdTab([string]$name) {
        $tab = $dialog.FindFirst($TS::Descendants, (New-Object Windows.Automation.AndCondition(
            (New-AdCondition $AE::NameProperty $name), (New-AdCondition $AE::ControlTypeProperty $CT::TabItem))))
        $tab.GetCurrentPattern([Windows.Automation.SelectionItemPattern]::Pattern).Select()
        Start-Sleep -Milliseconds 800
    }
    function Find-AdLevelList() { Get-AdLists $dialog | Where-Object { (Get-AdListItems $_) -contains $Auto } | Select-Object -First 1 }
    $algorithm = Get-AdLists $dialog | Where-Object { (Get-AdListItems $_) -contains 'SSIM' } | Select-Object -First 1
    $before = Get-AdListValue $algorithm
    Select-AdTab 'Advanced'
    $level = Find-AdLevelList
    Show-Check ([bool]$level) "(1) Advanced offers the level list"
    if ($level) {
        "  items: $((Get-AdListItems $level) -join ' | ')"
        Show-Check (-not $level.Current.IsEnabled) "(1) disabled for '$before'"
        Select-AdTab 'Compare'
        $algorithm = Get-AdLists $dialog | Where-Object { (Get-AdListItems $_) -contains 'SSIM' } | Select-Object -First 1
        Select-AdListItem $algorithm $Aligned
        Select-AdTab 'Advanced'
        $level = Find-AdLevelList
        Show-Check ($level.Current.IsEnabled) "(1) enabled for the aligned search"
        Show-Check ((Get-AdListValue $level) -eq $Auto) "(1) Auto in a fresh profile: '$(Get-AdListValue $level)'"
        if ($Shots) {
            # Every item, closed, as the list shows it: the longest must fit.
            $n = 0
            foreach ($item in Get-AdListItems $level) {
                Select-AdListItem $level $item
                Save-AdWindowPicture $dialog (Join-Path $Shots "options-advanced-$n.png")
                $n++
            }
        }
        Select-AdListItem $level $Highest
    }
    Send-AdButton $dialog 'OK'
    Start-Sleep -Seconds 2
    Stop-AdBuild $p $main
    $profile = Get-ChildItem -LiteralPath $s -Recurse -Filter default.xml | Select-Object -First 1
    $saved = ([xml](Get-Content -LiteralPath $profile.FullName -Raw -Encoding utf8)).SelectSingleNode('//compareOptions/alignedLevel').InnerText
    Show-Check ($saved -eq '3') "(2) the profile keeps level $saved"

    Test-AdWarning 'forced' 'Search will continue at your setting'
    Set-AdLevel 0
    Test-AdWarning 'auto' 'Searching for minimum crop size ~1/10 instead'
} finally {
    Stop-AdStrays
}
