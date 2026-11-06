# The preview's details in the running program: resolution and file name marks,
# selecting and copying, a key going on to the results list, the result counts,
# the images aligned to the divider and the Highlight button. Pictures go to
# <Shot>-<view>.png; prints ok/FAIL per check and PASS or FAIL at the end. The
# copy check overwrites the clipboard.
#   pwsh -File ui_preview_check.ps1 -Exe <bin\Release\AntiDupl.NET.WinForms.exe> -s <new scratch folder> -Folder <images> -Shot <prefix>
# <images>: two or more pictures of one image at different sizes, in two
# subfolders, so that the aspect ratio filter (turned off here) would part them.
param([string]$Exe, [string]$s, [string]$Folder, [string]$Shot, [string]$ColorMode = 'Classic')
. (Join-Path $PSScriptRoot 'ui_automation.ps1')
$script:failures = 0
function Check([string]$what, [string]$got, [string]$expected) {
    $ok = $got -eq $expected
    if (-not $ok) { $script:failures++ }
    "$(if ($ok) { 'ok  ' } else { 'FAIL' }) ${what}: '$got'$(if (-not $ok) { ", expected '$expected'" })"
}
function Set-Xml([string]$file, [hashtable]$values) {
    $x = [IO.File]::ReadAllText($file)
    foreach ($k in $values.Keys) {
        if ($x -cnotmatch "<$k>") { throw "no <$k> in $file" }
        $x = $x -creplace "<$k>[^<]*</$k>", "<$k>$($values[$k])</$k>"
    }
    [IO.File]::WriteAllText($file, $x)
}
function Start-Search() {
    $p = Start-Process -FilePath $Exe -ArgumentList '-s', "`"$s`"", '-search', "`"$Folder`"", '-start' -PassThru
    $script:AdStarted.Add($p)
    $byPid = New-AdCondition $AE::ProcessIdProperty $p.Id
    $deadline = (Get-Date).AddSeconds(40); $main = $null
    while (-not $main -and (Get-Date) -lt $deadline) {
        Start-Sleep -Seconds 1
        try {
            $main = @($AE::RootElement.FindAll($TS::Children, $byPid)) |
                Where-Object { $_.FindFirst($TS::Children, (New-AdCondition $AE::ControlTypeProperty $CT::ToolBar)) } | Select-Object -First 1
        } catch {}
    }
    if (-not $main) { throw "main window not found" }
    Start-Sleep -Seconds 8
    return @($p, $main)
}
function Lp([int]$x, [int]$y) { [IntPtr](($y -shl 16) -bor ($x -band 0xFFFF)) }

try {
    $p, $main = Start-AdBuild $Exe $s
    Stop-AdBuild $p $main
    $options = Join-Path $s 'options.xml'
    $settings = (Get-ChildItem -LiteralPath $s -Recurse -Filter default.xml | Select-Object -First 1).FullName
    Set-Xml $settings @{ ratioControl = 'false' }
    Set-Xml $settings @{ RatioControl = 'false' }

    foreach ($view in 'HorizontalPairTable', 'VerticalPairTable') {
        Set-Xml $options @{ colorMode = $ColorMode; ShowResultCounts = 'true'; AlignImagesToDivider = 'true'; viewMode = $view }
        $p, $main = Start-Search
        # WM_SYSCOMMAND, SC_MAXIMIZE: the vertical view's bars need the room.
        [AdUiNative]::PostMessage([IntPtr]$main.Current.NativeWindowHandle, 0x0112, [IntPtr]0xF030, [IntPtr]0) | Out-Null
        Start-Sleep -Seconds 2
        Save-AdWindowPicture $main "$Shot-$view.png"
        $texts = @($main.FindAll($TS::Descendants, (New-AdCondition $AE::ControlTypeProperty $CT::Text)))
        $path = $texts | Where-Object { $_.Current.Name -match '\\[^\\]+\.(png|jpg)$' } | Select-Object -First 1
        Check "$view, a path shows" ([bool]$path) 'True'
        # The vertical view's panel is too narrow to show a path.
        if ($path -and $view -eq 'HorizontalPairTable') {
            $h = [IntPtr]$path.Current.NativeWindowHandle
            $r = $path.Current.BoundingRectangle
            $y = [int]($r.Height / 2)
            [AdUiNative]::PostMessage($h, 0x201, [IntPtr]1, (Lp 20 $y)) | Out-Null   # WM_LBUTTONDOWN
            [AdUiNative]::PostMessage($h, 0x200, [IntPtr]1, (Lp 90 $y)) | Out-Null   # WM_MOUSEMOVE
            [AdUiNative]::PostMessage($h, 0x202, [IntPtr]0, (Lp 90 $y)) | Out-Null   # WM_LBUTTONUP
            Start-Sleep -Milliseconds 500
            Save-AdWindowPicture $main "$Shot-$view-selected.png"
            [AdUiNative]::PostMessage($h, 0x204, [IntPtr]2, (Lp 50 $y)) | Out-Null   # WM_RBUTTONDOWN
            [AdUiNative]::PostMessage($h, 0x205, [IntPtr]0, (Lp 50 $y)) | Out-Null   # WM_RBUTTONUP
            Start-Sleep -Seconds 1
            $copy = @($AE::RootElement.FindAll($TS::Children, (New-AdCondition $AE::ProcessIdProperty $p.Id))) | ForEach-Object {
                $_.FindFirst($TS::Descendants, (New-Object Windows.Automation.AndCondition(
                    (New-AdCondition $AE::NameProperty 'Copy'), (New-AdCondition $AE::ControlTypeProperty $CT::MenuItem))))
            } | Where-Object { $_ } | Select-Object -First 1
            Check "$view, the menu offers Copy" ([bool]$copy) 'True'
            if ($copy) {
                $copy.GetCurrentPattern([Windows.Automation.InvokePattern]::Pattern).Invoke()
                Start-Sleep -Milliseconds 500
                $clip = Get-Clipboard -Raw
                Check "$view, a part of the path copied ('$clip')" ($clip.Length -gt 3 -and $path.Current.Name.Contains($clip) -and $clip.Length -lt $path.Current.Name.Length) 'True'
            }

            # A key pressed in a label moves the list's row as it would there.
            [AdUiNative]::PostMessage($h, 0x201, [IntPtr]1, (Lp 20 $y)) | Out-Null
            [AdUiNative]::PostMessage($h, 0x200, [IntPtr]1, (Lp 90 $y)) | Out-Null
            [AdUiNative]::PostMessage($h, 0x202, [IntPtr]0, (Lp 90 $y)) | Out-Null
            Start-Sleep -Milliseconds 500
            [AdUiNative]::PostMessage($h, 0x100, [IntPtr]0x28, [IntPtr]1) | Out-Null  # WM_KEYDOWN, VK_DOWN
            Start-Sleep -Seconds 1
            $current = @($main.FindAll($TS::Descendants, [Windows.Automation.Condition]::TrueCondition)) |
                Where-Object { $_.Current.Name -match '^Current: ' } | Select-Object -First 1
            Check "$view, the key moved the list" $current.Current.Name 'Current: 2'
        }

        $toolbar = $main.FindFirst($TS::Children, (New-AdCondition $AE::ControlTypeProperty $CT::ToolBar))
        # The tool bar's one check box: it stays pressed.
        $button = $toolbar.FindFirst($TS::Children, (New-AdCondition $AE::ControlTypeProperty $CT::CheckBox))
        Check "$view, Highlight button" ([bool]$button) 'True'
        if ($button -and $view -eq 'HorizontalPairTable') {
            Send-AdClick $button $toolbar
            Start-Sleep -Seconds 2
            Save-AdWindowPicture $main "$Shot-highlight.png"
        }
        Stop-AdBuild $p $main
        if ($view -eq 'HorizontalPairTable') {
            Check 'highlighting saved on' ([bool](Select-String -LiteralPath $options -Pattern '<HighlightDifference>true</HighlightDifference>' -Quiet)) 'True'
        }
    }
} finally { Stop-AdStrays }
"$(if ($script:failures) { "FAIL: $script:failures" } else { 'PASS' })"
