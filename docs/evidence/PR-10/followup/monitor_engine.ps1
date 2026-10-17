param(
    [ValidateSet('full','p04','probe')][string]$Lane = 'probe'
)
# Starts and monitors only this review's own process; never another session.
$reviewRoot = (Resolve-Path (Join-Path $PSScriptRoot '../../../..')).Path
$reviewPython = (Get-Command python).Source
$env:POB2_ROOT = 'C:/Users/Elias/PycharmProjects/PathOfBuilding-PoE2'
$reviewArgs = switch ($Lane) {
    'full' { @('-m','pytest','tests/engine','-q','-p','no:cacheprovider') }
    'p04' { @('-m','pytest','tests/engine/test_p04_round_trips.py','-q','-p','no:cacheprovider') }
    'probe' { @('docs/evidence/PR-10/followup/review_followup.py','--engine') }
}
$reviewOut = Join-Path $PSScriptRoot "$Lane-stdout.txt"
$reviewErr = Join-Path $PSScriptRoot "$Lane-stderr.txt"
$reviewProcess = Start-Process -FilePath $reviewPython -ArgumentList $reviewArgs -WorkingDirectory $reviewRoot -WindowStyle Hidden -PassThru -RedirectStandardOutput $reviewOut -RedirectStandardError $reviewErr
$reviewTimer = [Diagnostics.Stopwatch]::StartNew()
$reviewPeak = 0L
$reviewStopped = $false
while (-not $reviewProcess.HasExited) {
    $reviewProcess.Refresh()
    $reviewPeak = [Math]::Max($reviewPeak, $reviewProcess.WorkingSet64)
    if ($reviewProcess.WorkingSet64 -gt 4GB -or $reviewTimer.Elapsed.TotalSeconds -gt 240) {
        Stop-Process -Id $reviewProcess.Id
        $reviewStopped = $true
        break
    }
    Start-Sleep -Seconds 2
}
$reviewProcess.WaitForExit()
$reviewResult = @{exit_code=$reviewProcess.ExitCode; stopped_at_limit=$reviewStopped; peak_working_set_bytes=$reviewPeak; elapsed_seconds=$reviewTimer.Elapsed.TotalSeconds}
$reviewResult | ConvertTo-Json | Set-Content -Encoding utf8 (Join-Path $PSScriptRoot "$Lane-monitor.json")
$reviewResult | ConvertTo-Json
Get-Content $reviewOut -Tail 12
