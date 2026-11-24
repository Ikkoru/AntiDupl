# Checks the aligned search's level and time settings, its warnings and its
# progress line in the running program, in a new scratch settings folder
# (PowerShell 7). -Many is a folder of so many pictures that the highest
# level's keypoints don't fit in the free memory and no level's search fits
# in 15 minutes (many_images.py beside it makes one): the highest level
# counts about 0.4 MB a picture against what is free, less a tenth of all
# the memory (1 GB at least) and the image cache.
# (1) Options > Advanced offers the level list and the time limit, enabled
# whatever the algorithm (their labels say they are the aligned search's),
# Auto and 15 minutes in a fresh profile; (2) the profile keeps the level
# chosen and the limit; (3) with the highest level set, a search of -Many
# shows the time warning as it starts, while it runs, with the text for a
# level kept though it takes longer than the limit; the search's window
# says the crop size and the time; closing the warning brings the memory
# warning, whose Stop button stops the search; it stays once the search has
# ended, its Stop button off; (4) with Auto and the limit, the time warning
# says the search looks for larger crops or at the lightest setting, and
# its Stop button stops the search with no memory warning after; (5) with
# Auto and no limit, only the memory warning shows, saying the search looks
# for larger crops instead (or that even the lightest setting doesn't fit).
# When the highest level fits in the memory free, the memory steps print
# SKIP. -Many's pictures have few keypoints: its searches end in seconds.
# -Shots names a folder for pictures of the dialog and of each warning.
# Prints one line per check, PASS or FAIL.
#   ui_aligned_level_check.ps1 -Exe <exe> -s <new scratch folder> -Many <folder> [-Shots <folder>]
param([string]$Exe, [string]$s, [string]$Many, [string]$Shots)
. (Join-Path $PSScriptRoot 'ui_automation.ps1')
$Aligned = 'Aligned perceptual (crops, shifts)'
$Auto = 'Auto: limited by memory and time'
$Highest = '1/100 of image, 4.0 GB per 10k files'
$TimeLimitLabel = 'Aligned search time limit, minutes (0 = none)'
$MemoryTitle = 'Not enough memory for the smallest crops'
$TimeTitle = 'Not enough time for the smallest crops'
function Show-Check([bool]$ok, [string]$text) { '{0} {1}' -f $(if ($ok) { 'PASS' } else { 'FAIL' }), $text }

# Sets a profile value of the aligned search (both copies the profile keeps,
# the field's and the property's).
function Set-AdAligned([string]$field, [int]$value) {
    $profile = Get-ChildItem -LiteralPath $s -Recurse -Filter default.xml | Select-Object -First 1
    $x = [xml](Get-Content -LiteralPath $profile.FullName -Raw -Encoding utf8)
    $property = $field.Substring(0, 1).ToUpper() + $field.Substring(1)
    foreach ($name in $field, $property) { $x.SelectSingleNode("//compareOptions/$name").InnerText = "$value" }
    $x.Save($profile.FullName)
}

# A window of the process titled so, a window of its own or one inside
# another (dialogs owned by the main window are in UI Automation's tree
# there); null when none shows within the seconds given.
function Wait-AdWindow($p, [string]$title, [int]$seconds) {
    $byPid = New-AdCondition $AE::ProcessIdProperty $p.Id
    $isWindow = New-AdCondition $AE::ControlTypeProperty $CT::Window
    for ($i = 0; $i -lt $seconds; $i++) {
        try {
            foreach ($top in @($AE::RootElement.FindAll($TS::Children, $byPid))) {
                if ($top.Current.Name -eq $title) { return $top }
                $inner = @($top.FindAll($TS::Children, $isWindow)) | Where-Object { $_.Current.Name -eq $title } | Select-Object -First 1
                if ($inner) { return $inner }
            }
        } catch {}
        Start-Sleep -Seconds 1
    }
    $null
}

function Start-AdManySearch() {
    $p = Start-Process -FilePath $Exe -ArgumentList '-s', "`"$s`"", '-search', "`"$Many`"", '-start' -PassThru
    $script:AdStarted.Add($p)
    $p
}

function Get-AdWarningText($warning) {
    (@($warning.FindAll($TS::Descendants, (New-AdCondition $AE::ControlTypeProperty $CT::Text))) | ForEach-Object { $_.Current.Name }) -join ' '
}

function Get-AdWarningButton($warning, [string]$name) {
    $warning.FindFirst($TS::Descendants, (New-Object Windows.Automation.AndCondition(
        (New-AdCondition $AE::NameProperty $name), (New-AdCondition $AE::ControlTypeProperty $CT::Button))))
}

function Push-AdButton($warning, [string]$name) {
    $button = Get-AdWarningButton $warning $name
    [AdUiNative]::PostMessage([IntPtr]$button.Current.NativeWindowHandle, 0x00F5, [IntPtr]0, [IntPtr]0) | Out-Null
}

# The search's progress window, while the search runs.
function Test-AdSearching($p) {
    # The progress window's title starts so while the search runs; a window
    # closing as it is read makes UI Automation throw, and is read again.
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

# A warning's text against what it should say (any of several).
function Test-AdText($warning, [string]$label, [string[]]$expected) {
    $text = Get-AdWarningText $warning
    "  $text"
    $match = $expected | Where-Object { $text -like "*$_*" } | Select-Object -First 1
    Show-Check ([bool]$match) "($label) it says: '$(if ($match) { $match } else { $expected -join "' or '" })'"
    if ($Shots) { Save-AdWindowPicture $warning (Join-Path $Shots "warning-$label.png") }
}

# Stops the search with the warning's Stop button; the warning stays.
function Test-AdStop($p, $warning, [string]$label, [string]$title) {
    Push-AdButton $warning 'Stop search'
    $ended = $false
    for ($i = 0; $i -lt 120 -and -not $ended; $i++) { Start-Sleep -Seconds 1; $ended = -not (Test-AdSearching $p) }
    Show-Check $ended "($label) its Stop button stops the search"
    Start-Sleep -Seconds 2
    $still = $false; $stopOff = $false
    try { $still = $warning.Current.Name -eq $title; $stopOff = -not (Get-AdWarningButton $warning 'Stop search').Current.IsEnabled } catch {}
    Show-Check ($still -and $stopOff) "($label) the warning stays once the search has ended, its Stop button off"
}

function Stop-AdSearchBuild($p) {
    $main = Get-AdMain $p
    if ($main) { Stop-AdBuild $p $main } else { Stop-Process -Id $p.Id }
}

# (3) The highest level set: the time warning, then on Close the memory one.
function Test-AdForced() {
    $p = Start-AdManySearch
    $time = Wait-AdWindow $p $TimeTitle 180
    Show-Check ([bool]$time) "(forced) the time warning shows as the search starts"
    if (-not $time) { Stop-Process -Id $p.Id; return }
    Test-AdText $time 'forced-time' @('Search will continue at your setting.')
    $running = Test-AdSearching $p
    Show-Check $running "(forced) the search runs meanwhile"
    Show-Check ($script:AdWindowNames -like '*crops down to ~1/*, ~* total*') "(forced) the search's window says the crop size and the time"
    "  windows: $script:AdWindowNames"
    Show-Check (-not (Wait-AdWindow $p $MemoryTitle 2)) "(forced) no memory warning while the time warning is open"
    Push-AdButton $time 'Close'
    $memory = Wait-AdWindow $p $MemoryTitle 15
    if (-not $memory) {
        'SKIP (forced) no memory warning after the time warning: the highest level fits in the memory free now'
    } else {
        Show-Check $true "(forced) closing the time warning brings the memory warning"
        Test-AdText $memory 'forced-memory' @('Search will continue at your setting, but Windows')
        Test-AdStop $p $memory 'forced-memory' $MemoryTitle
        Push-AdButton $memory 'Close'
    }
    Start-Sleep -Seconds 1
    Stop-AdSearchBuild $p
}

# (4) Auto with the limit: the time warning's Stop, and no memory warning.
function Test-AdAutoTime() {
    $p = Start-AdManySearch
    $time = Wait-AdWindow $p $TimeTitle 180
    Show-Check ([bool]$time) "(auto-time) the time warning shows as the search starts"
    if (-not $time) { Stop-Process -Id $p.Id; return }
    Test-AdText $time 'auto-time' @('Searching for minimum crop size ~1/', 'Search will continue at the lightest setting.')
    Test-AdStop $p $time 'auto-time' $TimeTitle
    Push-AdButton $time 'Close'
    Show-Check (-not (Wait-AdWindow $p $MemoryTitle 5)) "(auto-time) no memory warning once the search was stopped"
    Stop-AdSearchBuild $p
}

# (5) Auto with no limit: the memory warning alone.
function Test-AdAutoMemory() {
    $p = Start-AdManySearch
    $memory = Wait-AdWindow $p $MemoryTitle 60
    if (-not $memory) {
        'SKIP (auto) no memory warning: the highest level fits in the memory free now'
        Show-Check (-not (Wait-AdWindow $p $TimeTitle 1)) "(auto) no time warning with no limit"
        if (-not $p.HasExited) { Stop-AdSearchBuild $p }
        return
    }
    Show-Check $true "(auto) the memory warning shows as the search starts"
    Show-Check (-not (Wait-AdWindow $p $TimeTitle 1)) "(auto) no time warning with no limit"
    # Too little memory for even the lowest level says so instead.
    Test-AdText $memory 'auto' @('Searching for minimum crop size ~1/', 'for lightest setting')
    Test-AdStop $p $memory 'auto' $MemoryTitle
    Push-AdButton $memory 'Close'
    Start-Sleep -Seconds 1
    Stop-AdSearchBuild $p
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
    # The time limit's label, enabled with its box; the boxes' values.
    function Find-AdTimeLimit() {
        $dialog.FindFirst($TS::Descendants, (New-Object Windows.Automation.AndCondition(
            (New-AdCondition $AE::NameProperty $TimeLimitLabel), (New-AdCondition $AE::ControlTypeProperty $CT::Text))))
    }
    function Get-AdTimeLimitValue() {
        $edits = @($dialog.FindAll($TS::Descendants, (New-AdCondition $AE::ControlTypeProperty $CT::Edit)))
        @($edits | ForEach-Object { $_.GetCurrentPattern([Windows.Automation.ValuePattern]::Pattern).Current.Value })
    }
    $algorithm = Get-AdLists $dialog | Where-Object { (Get-AdListItems $_) -contains 'SSIM' } | Select-Object -First 1
    $before = Get-AdListValue $algorithm
    Select-AdTab 'Advanced'
    $level = Find-AdLevelList
    Show-Check ([bool]$level) "(1) Advanced offers the level list"
    $limit = Find-AdTimeLimit
    Show-Check ([bool]$limit) "(1) Advanced offers the time limit"
    if ($level) {
        "  items: $((Get-AdListItems $level) -join ' | ')"
        Show-Check ($level.Current.IsEnabled) "(1) the level list enabled for '$before'"
        if ($limit) { Show-Check ($limit.Current.IsEnabled) "(1) the time limit enabled for '$before'" }
        Show-Check ((Get-AdListValue $level) -eq $Auto) "(1) Auto in a fresh profile: '$(Get-AdListValue $level)'"
        $values = Get-AdTimeLimitValue
        Show-Check ($values -contains '15') "(1) the time limit 15 in a fresh profile (boxes: $($values -join ', '))"
        Select-AdTab 'Compare'
        $algorithm = Get-AdLists $dialog | Where-Object { (Get-AdListItems $_) -contains 'SSIM' } | Select-Object -First 1
        Select-AdListItem $algorithm $Aligned
        Select-AdTab 'Advanced'
        $level = Find-AdLevelList
        Show-Check ($level.Current.IsEnabled) "(1) the level list enabled for the aligned search"
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
    $x = [xml](Get-Content -LiteralPath $profile.FullName -Raw -Encoding utf8)
    $saved = $x.SelectSingleNode('//compareOptions/alignedLevel').InnerText
    Show-Check ($saved -eq '4') "(2) the profile keeps level $saved"
    $savedLimit = $x.SelectSingleNode('//compareOptions/alignedTimeLimit').InnerText
    Show-Check ($savedLimit -eq '15') "(2) the profile keeps the time limit $savedLimit"

    Test-AdForced
    Set-AdAligned 'alignedLevel' 0
    Test-AdAutoTime
    Set-AdAligned 'alignedTimeLimit' 0
    Test-AdAutoMemory
} finally {
    Stop-AdStrays
}
