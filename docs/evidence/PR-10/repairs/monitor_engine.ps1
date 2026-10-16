param(
    [ValidateSet('full','p04','f11')][string]$Lane = 'full',
    [string]$Run = 'baseline',
    [string]$Python = 'python',
    [switch]$Trace,
    [string]$Workspace = '',
    [switch]$Quiet
)
# Starts and monitors only this review's own process; never another session.
$reviewRoot = (Resolve-Path (Join-Path $PSScriptRoot '../../../..')).Path
if ($Workspace) { $reviewRoot = (Resolve-Path $Workspace).Path }
$reviewPython = (Get-Command $Python).Source
$env:POB2_ROOT = 'C:/Users/Elias/PycharmProjects/PathOfBuilding-PoE2'
$env:PYTHONPATH = "$reviewRoot/pob2-mcp;$reviewRoot/pob2-optimizer;$PSScriptRoot"
$reviewArgs = switch ($Lane) {
    'full' { @('-m','pytest','tests/engine','-vv','-p','no:cacheprovider') }
    'p04' { @('-m','pytest','tests/engine/test_p04_round_trips.py','-vv','-p','no:cacheprovider') }
    'f11' { @('-m','pytest','tests/engine/test_f11_import_is_wiped.py','-vv','-p','no:cacheprovider') }
}
if ($Quiet) { $reviewArgs = $reviewArgs | ForEach-Object { if ($_ -eq '-vv') { '-q' } else { $_ } } }
if ($Trace) {
    $reviewArgs += @('-p','engine_trace')
    $env:POB2_TRACE_FILE = Join-Path $PSScriptRoot "$Run-$Lane-calls.jsonl"
}
$reviewOut = Join-Path $PSScriptRoot "$Run-$Lane-stdout.txt"
$reviewErr = Join-Path $PSScriptRoot "$Run-$Lane-stderr.txt"
$reviewProcess = Start-Process -FilePath $reviewPython -ArgumentList $reviewArgs -WorkingDirectory $reviewRoot -WindowStyle Hidden -PassThru -RedirectStandardOutput $reviewOut -RedirectStandardError $reviewErr
$reviewTimer = [Diagnostics.Stopwatch]::StartNew()
$reviewPeak = 0L
$reviewStopped = $false
$reviewSamples = @()
while (-not $reviewProcess.HasExited) {
    $reviewProcess.Refresh()
    # Include descendants: Windows venv python.exe can be only a launcher.
    $reviewAll = @(Get-CimInstance Win32_Process)
    $reviewIds = @($reviewProcess.Id)
    do {
        $reviewAdded = @($reviewAll | Where-Object { $_.ParentProcessId -in $reviewIds -and $_.ProcessId -notin $reviewIds })
        $reviewIds += @($reviewAdded | ForEach-Object { $_.ProcessId })
    } while ($reviewAdded.Count)
    $reviewOwned = @($reviewAll | Where-Object { $_.ProcessId -in $reviewIds })
    $reviewBytes = ($reviewOwned | Measure-Object -Property WorkingSetSize -Sum).Sum
    $reviewPeak = [Math]::Max($reviewPeak, $reviewBytes)
    $reviewSamples += @{seconds=$reviewTimer.Elapsed.TotalSeconds; bytes=$reviewBytes; progress=(Get-Content $reviewOut -Tail 1)}
    if ($reviewBytes -gt 4GB -or $reviewTimer.Elapsed.TotalSeconds -gt 240) {
        $reviewOwned | Where-Object { $_.ProcessId -ne $reviewProcess.Id } | ForEach-Object { Stop-Process -Id $_.ProcessId -ErrorAction SilentlyContinue }
        Stop-Process -Id $reviewProcess.Id
        $reviewStopped = $true
        break
    }
    Start-Sleep -Seconds 2
}
$reviewProcess.WaitForExit()
$reviewResult = @{exit_code=$reviewProcess.ExitCode; stopped_at_limit=$reviewStopped; peak_working_set_bytes=$reviewPeak; elapsed_seconds=$reviewTimer.Elapsed.TotalSeconds; samples=$reviewSamples}
$reviewResult | ConvertTo-Json -Depth 5 | Set-Content -Encoding utf8 (Join-Path $PSScriptRoot "$Run-$Lane-monitor.json")
$reviewResult | Select-Object exit_code,stopped_at_limit,peak_working_set_bytes,elapsed_seconds | ConvertTo-Json
Get-Content $reviewOut -Tail 12
