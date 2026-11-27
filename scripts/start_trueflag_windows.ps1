param(
    [ValidateSet('Initialize', 'Start', 'Status', 'Stop', 'Restart')]
    [string]$Action = 'Start',
    [string]$PostgresBin = '',
    [switch]$StopDatabase
)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$pythonPath = Join-Path $projectRoot '.venv-windows\Scripts\python.exe'
$runtimeScript = Join-Path $PSScriptRoot 'windows_runtime.py'
if (-not (Test-Path -LiteralPath $pythonPath)) { throw 'Install the pinned .venv-windows environment first.' }
if ($Action -eq 'Initialize') {
    if (-not $PostgresBin) { throw 'Supply the native PostgreSQL bin directory.' }
    & $pythonPath $runtimeScript initialize --pg-bin $PostgresBin
} elseif ($Action -eq 'Start' -or $Action -eq 'Restart') {
    if ($Action -eq 'Start') {
        $existingStatus = & $pythonPath $runtimeScript status | ConvertFrom-Json
        if ($LASTEXITCODE -eq 0 -and $existingStatus.ready) {
            $existingStatus | ConvertTo-Json -Compress
            exit 0
        }
    }
    if ($Action -eq 'Restart') {
        & $pythonPath $runtimeScript stop
        if ($LASTEXITCODE -ne 0) { throw 'Shutdown did not complete; preserving runtime.' }
    }
    # Quoted argument paths; fixed script/action, no credentials in argv.
    $consoleLog = Join-Path $projectRoot 'runtime\windows-native\supervisor-console.log'
    $consoleError = Join-Path $projectRoot 'runtime\windows-native\supervisor-error.log'
    $process = Start-Process -FilePath $pythonPath -ArgumentList ('"{0}" supervise' -f $runtimeScript) -WorkingDirectory $projectRoot -WindowStyle Hidden -PassThru -RedirectStandardOutput $consoleLog -RedirectStandardError $consoleError
    $ready = $false
    for ($attempt = 0; $attempt -lt 25; $attempt++) {
        Start-Sleep -Seconds 2
        if ($process.HasExited) { throw 'Native supervisor failed. Inspect the private runtime logs.' }
        $status = & $pythonPath $runtimeScript status | ConvertFrom-Json
        if ($status.ready) { $ready = $true; $status | ConvertTo-Json -Compress; break }
    }
    if (-not $ready) { throw 'Native readiness did not pass. Processes and private diagnostics are preserved.' }
} else {
    if ($Action -eq 'Stop' -and $StopDatabase) {
        & $pythonPath $runtimeScript stop --stop-database
    } else {
        & $pythonPath $runtimeScript $Action.ToLowerInvariant()
    }
}
if ($LASTEXITCODE -ne 0) { throw 'Native runtime action failed; credentials were not printed.' }
