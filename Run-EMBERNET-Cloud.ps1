param(
    [ValidateSet('nikhilthakuraan','ieirodov14')][string]$Profile='nikhilthakuraan',
    [ValidateRange(30,1200)][int]$Seconds=600,
    [switch]$RotateControlCode,
    [ValidateSet('RTX-PRO-6000','L40S')][string]$Gpu='RTX-PRO-6000',
    [ValidateSet('city','wildland')][string]$World='city'
)
$ErrorActionPreference='Stop'
Set-Location -LiteralPath $PSScriptRoot
$python=Join-Path $PSScriptRoot '.venv-embernet/Scripts/python.exe'
$consent=Join-Path $PSScriptRoot 'artifacts/embernet/isaac/license-consent.json'
if (!(Test-Path -LiteralPath $consent) -or !((Get-Content -Raw -LiteralPath $consent | ConvertFrom-Json).accepted)) {
    throw 'NVIDIA license consent is required. See context/ISAAC_SIM.md.'
}
$env:MODAL_PROFILE=$Profile
$env:PYTHONUTF8='1'
if (!(Test-Path -LiteralPath 'artifacts/embernet/isaac/nvidia-tower/pack/Demos/AEC/TowerDemo/CityTowerDemopack/Assemblies/assembly_BaseBuilding.usd')) {
    & $python tools/fetch_nvidia_tower.py
    if ($LASTEXITCODE -ne 0) {throw 'NVIDIA architectural asset preparation failed'}
}
& $python -m modal deploy cloud_live.py
if ($LASTEXITCODE -ne 0) {throw 'Cloud gateway deployment failed'}
$arguments=@('-m','modal','run','cloud_live.py','--duration',"$Seconds",'--gpu',$Gpu,'--world',$World)
if ($RotateControlCode) {$arguments+='--rotate'}
& $python @arguments
if ($LASTEXITCODE -ne 0) {throw 'No new session voucher issued; inspect the error'}
Write-Host 'Private control invite: artifacts/embernet/cloud/control-invite.private.json'
