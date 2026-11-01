param(
    [ValidateSet('boot', 'flight', 'fleet')][string]$Mode = 'flight',
    [ValidateSet('nikhilthakuraan', 'ieirodov14')][string]$Profile = 'nikhilthakuraan',
    [switch]$AcceptNvidiaEula
)
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
if (-not $AcceptNvidiaEula) {
    throw 'Read the NVIDIA terms in context/ISAAC_SIM.md, then pass -AcceptNvidiaEula to acknowledge them.'
}
$python = Join-Path $PSScriptRoot '.venv-embernet/Scripts/python.exe'
if (-not (Test-Path -LiteralPath $python)) { throw 'Run Setup-EMBERNET.ps1 first.' }
& $python tools/fetch_simready_assets.py
if ($LASTEXITCODE -ne 0) { throw 'NVIDIA asset download failed integrity validation.' }
$env:MODAL_PROFILE = $Profile
$env:EMBERNET_ISAAC_VERSION = '6.2.0.0'
$env:PYTHONUTF8 = '1'
& $python tools/fetch_nvidia_vegetation.py
if ($LASTEXITCODE -ne 0) { throw 'NVIDIA vegetation failed integrity validation.' }
$runId = 'isaac62-' + $Mode + '-' + [DateTime]::UtcNow.ToString('yyyyMMdd-HHmmss-fff')
& $python -m modal run cloud_isaac_runtime.py --accept-nvidia-eula --mode $Mode --run-id $runId
if ($LASTEXITCODE -ne 0) { throw "Trial failed. Inspect artifacts/embernet/isaac/$runId for saved diagnostics." }
Write-Host "Downloaded evidence: artifacts/embernet/isaac/$runId"
