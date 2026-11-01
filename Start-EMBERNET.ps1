param([switch]$ControlPanel, [switch]$Reference, [switch]$TelemetryOnly, [switch]$Rerun)
$ErrorActionPreference = 'Stop'
$projectRoot = $PSScriptRoot
$python = Join-Path $projectRoot '.venv-embernet\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python)) {
    throw 'Run Setup-EMBERNET.ps1 first to install the local environment.'
}
$logDirectory = Join-Path $projectRoot 'artifacts\embernet'
New-Item -ItemType Directory -Force -Path $logDirectory | Out-Null
$ready = $false
try { $null = Invoke-RestMethod 'http://127.0.0.1:8780/api/state' -TimeoutSec 2; $ready = $true } catch {}
if (-not $ready) {
    $serverArguments = @('-m','embernet','serve')
    if ($Rerun -or $TelemetryOnly) { $serverArguments += '--rerun' }
    Start-Process -FilePath $python -ArgumentList $serverArguments -WorkingDirectory $projectRoot -WindowStyle Hidden -RedirectStandardOutput (Join-Path $logDirectory 'server.log') -RedirectStandardError (Join-Path $logDirectory 'server-errors.log')
    for ($attempt = 0; $attempt -lt 30; $attempt++) {
        Start-Sleep -Milliseconds 500
        try { $null = Invoke-RestMethod 'http://127.0.0.1:8780/api/state' -TimeoutSec 2; $ready = $true; break } catch {}
    }
}
if (-not $ready) { throw 'Mission control did not start. See artifacts/embernet/server-errors.log.' }
if ($ControlPanel) {
    Start-Process 'http://127.0.0.1:8780'
} else {
    $learnedModels = Join-Path $projectRoot 'artifacts\embernet\embernet-v2\mission.pt'
    if ((Test-Path -LiteralPath $learnedModels) -and -not $Reference) {
        $null = Invoke-RestMethod 'http://127.0.0.1:8780/api/reset' -Method Post -ContentType 'application/json' -Body '{"sensor":"learned","policy":"learned"}'
        Write-Host 'Launching the learned prototype and mission policy in the forest simulation.'
    } else {
        $null = Invoke-RestMethod 'http://127.0.0.1:8780/api/reset' -Method Post -ContentType 'application/json' -Body '{"sensor":"reference","policy":"baseline"}'
        Write-Host 'Launching reference sensors and the explicit rule-based baseline in Rerun.'
    }
    $null = Invoke-RestMethod 'http://127.0.0.1:8780/api/control' -Method Post -ContentType 'application/json' -Body '{"action":"launch"}'
    if (-not $TelemetryOnly) { Start-Process 'http://127.0.0.1:8780' }
    Write-Host 'Live 3D simulation: http://127.0.0.1:8780. Rerun recordings are saved alongside it.'
}
