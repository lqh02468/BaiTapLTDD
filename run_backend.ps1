$ErrorActionPreference = 'Stop'
$pythonPath = Join-Path $PSScriptRoot '.tool\face_venv\Scripts\python.exe'
if (-not (Test-Path $pythonPath)) {
    throw 'Run .\setup_face.ps1 once before starting the backend.'
}
& $pythonPath (Join-Path $PSScriptRoot 'backend\server.py')
