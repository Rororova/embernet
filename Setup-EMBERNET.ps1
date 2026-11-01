$ErrorActionPreference = 'Stop'
Push-Location $PSScriptRoot
try {
    $env:UV_CACHE_DIR = Join-Path $PSScriptRoot '.cache\uv'
    $env:UV_PYTHON_INSTALL_DIR = Join-Path $PSScriptRoot '.cache\embernet-python'
    uv python install 3.12
    if ($LASTEXITCODE -ne 0) { throw 'Python installation failed' }
    uv venv --python 3.12 .venv-embernet
    if ($LASTEXITCODE -ne 0) { throw 'Environment creation failed' }
    uv pip install --python .venv-embernet/Scripts/python.exe -e '.[dev,learning,perception]'
    if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed' }
    .venv-embernet/Scripts/python.exe -m embernet.visual_assets
    if ($LASTEXITCODE -ne 0) { throw '3D scene asset generation failed' }
} finally { Pop-Location }
