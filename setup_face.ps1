$ErrorActionPreference = 'Stop'
$projectRoot = $PSScriptRoot
$pythonPath = Join-Path $projectRoot '.tool\face_venv\Scripts\python.exe'
if (-not (Test-Path $pythonPath)) {
    python -m venv (Join-Path $projectRoot '.tool\face_venv')
    if ($LASTEXITCODE -ne 0) { throw 'Cannot create Python environment for face recognition.' }
}
& $pythonPath -m pip install -r (Join-Path $projectRoot 'backend\requirements-face.txt')
if ($LASTEXITCODE -ne 0) { throw 'Cannot install OpenCV/numpy.' }
Write-Host 'Local face recognition dependencies are installed.'
