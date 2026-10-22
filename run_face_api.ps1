$ErrorActionPreference = 'Stop'
$root = $PSScriptRoot
$env:DOTNET_CLI_HOME = Join-Path $root '.tool\dotnet_home'
$env:NUGET_PACKAGES = Join-Path $root '.tool\nuget'
$env:DOTNET_CLI_TELEMETRY_OPTOUT = '1'
$feed = Join-Path $root '.tool\nuget_feed'
if (-not (Test-Path $feed)) { New-Item -ItemType Directory -Path $feed | Out-Null }
python (Join-Path $root 'LeQuangHuyApi\restore_packages.py') $feed
if ($LASTEXITCODE -ne 0) { throw 'Cannot download Face API dependencies.' }
dotnet restore (Join-Path $root 'LeQuangHuyApi\LeQuangHuyApi.csproj') --source $feed
if ($LASTEXITCODE -ne 0) { throw 'Face API restore failed.' }
dotnet run --no-restore --project (Join-Path $root 'LeQuangHuyApi\LeQuangHuyApi.csproj') --urls http://0.0.0.0:8081
