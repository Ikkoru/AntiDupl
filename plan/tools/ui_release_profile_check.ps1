# A build started with -s on a settings folder whose options.xml names a
# profile in the release's settings folder must not load or write that
# profile: it says so in a message and uses its own folder's profile. Runs
# on a scratch "release" folder (ANTIDUPL_RELEASE_SETTINGS), never the real
# one, so a failing build writes only there. Prints ok/FAIL per check and
# PASS or FAIL at the end. -Unguarded runs without the variable, which a
# working build must FAIL (the scratch folder is then not guarded).
#   pwsh -File ui_release_profile_check.ps1 -Exe <bin\Release\AntiDupl.NET.WinForms.exe> -Scratch <new folder> -From <a dev settings folder> [-Unguarded]
param([string]$Exe, [string]$Scratch, [string]$From, [switch]$Unguarded)
. (Join-Path $PSScriptRoot 'ui_automation.ps1')
$script:failures = 0
function Check([string]$what, [bool]$ok) {
    if (-not $ok) { $script:failures++ }
    "$(if ($ok) { 'ok  ' } else { 'FAIL' }) $what"
}
if (Test-Path -LiteralPath $Scratch) { throw "not a new folder: $Scratch" }
$release = Join-Path $Scratch 'release'
$profiles = Join-Path $release 'user\profiles'
$settings = Join-Path $Scratch 'settings'
New-Item -ItemType Directory -Path $profiles, (Join-Path $settings 'profiles') | Out-Null
Copy-Item -LiteralPath (Join-Path $From 'profiles\default.xml') -Destination $profiles
$releaseProfile = Join-Path $profiles 'default.xml'
$before = (Get-FileHash -LiteralPath $releaseProfile).Hash
$x = [xml](Get-Content -LiteralPath (Join-Path $From 'options.xml') -Raw -Encoding utf8)
$x.SelectSingleNode('//coreOptionsFileName').InnerText = $releaseProfile
$x.Save((Join-Path $settings 'options.xml'))

if (-not $Unguarded) { $env:ANTIDUPL_RELEASE_SETTINGS = $release }
try {
    $p = Start-Process -FilePath $Exe -ArgumentList '-s', "`"$settings`"" -PassThru
    $script:AdStarted.Add($p)
    # The message shows while the main window starts, over it or before it:
    # look for it the whole while rather than stopping at the main window.
    $byPid = New-AdCondition $AE::ProcessIdProperty $p.Id
    $message = $null
    $deadline = (Get-Date).AddSeconds(25)
    while (-not $message -and (Get-Date) -lt $deadline) {
        Start-Sleep -Milliseconds 700
        try {
            $message = @($AE::RootElement.FindAll($TS::Descendants, $byPid)) |
                Where-Object { $_.Current.ControlType -eq $CT::Window } | Where-Object {
                    @($_.FindAll($TS::Descendants, (New-AdCondition $AE::ControlTypeProperty $CT::Text)) |
                        Where-Object { $_.Current.Name -like '*belongs to the AntiDupl*' }).Count -gt 0
                } | Select-Object -First 1
        } catch {}
    }
    Check 'a message says the profile belongs to the release' ($null -ne $message)
    if ($message) { Send-AdButton $message 'OK' }
    $main = $null
    $deadline = (Get-Date).AddSeconds(30)
    while (-not $main -and (Get-Date) -lt $deadline) {
        Start-Sleep -Milliseconds 700
        try {
            $main = @($AE::RootElement.FindAll($TS::Children, $byPid)) |
                Where-Object { $_.FindFirst($TS::Children, (New-AdCondition $AE::ControlTypeProperty $CT::ToolBar)) } |
                Select-Object -First 1
        } catch {}
    }
    Stop-AdBuild $p $main
    $saved = ([xml](Get-Content -LiteralPath (Join-Path $settings 'options.xml') -Raw -Encoding utf8)).SelectSingleNode('//coreOptionsFileName').InnerText
    Check "options.xml now names this folder's profile ($saved)" ($saved -eq (Join-Path $settings 'profiles\default.xml'))
    Check "the release's profile is unchanged" ((Get-FileHash -LiteralPath $releaseProfile).Hash -eq $before)
    Check "nothing new in the release's profiles folder" (@(Get-ChildItem -LiteralPath $profiles).Count -eq 1)
} finally {
    Remove-Item Env:ANTIDUPL_RELEASE_SETTINGS -ErrorAction SilentlyContinue
    Stop-AdStrays
}
if ($script:failures) { "FAIL ($script:failures)" } else { 'PASS' }
