param([string]$DeviceId)

$ErrorActionPreference = 'Stop'
$adbCommand = Get-Command adb -ErrorAction SilentlyContinue
$adbPath = if ($adbCommand) { $adbCommand.Source } elseif (Test-Path 'D:\Android\platform-tools\adb.exe') {
    'D:\Android\platform-tools\adb.exe'
} else {
    throw 'Không tìm thấy adb. Cài Android platform-tools hoặc thêm adb vào PATH.'
}

try {
    $health = Invoke-RestMethod -Uri 'http://127.0.0.1:8080/health' -TimeoutSec 5
    if ($health.status -ne 'ok') { throw 'API không trả trạng thái ok.' }
} catch {
    throw 'API chưa chạy tại http://127.0.0.1:8080. Hãy chạy .\run_backend.ps1 trước.'
}

$ready = @(& $adbPath devices | Where-Object { $_ -match '\sdevice$' } |
    ForEach-Object { ($_ -split '\s+')[0] })
if (-not $ready) { throw 'ADB chưa thấy điện thoại ở trạng thái device. Kiểm tra USB debugging và chấp nhận quyền trên điện thoại.' }
if (-not $DeviceId) {
    if ($ready.Count -ne 1) { throw 'Có nhiều thiết bị. Chạy lại với -DeviceId <id>.' }
    $DeviceId = $ready[0]
}
if ($DeviceId -notin $ready) { throw "Thiết bị $DeviceId không ở trạng thái device." }

& $adbPath -s $DeviceId reverse tcp:8080 tcp:8080
if ($LASTEXITCODE -ne 0) { throw 'Không tạo được adb reverse.' }
Write-Host "ADB reverse đã bật cho $DeviceId. API: http://127.0.0.1:8080"

Push-Location (Join-Path $PSScriptRoot 'mobile')
try {
    flutter pub get
    if ($LASTEXITCODE -ne 0) { throw 'flutter pub get thất bại.' }
    flutter run -d $DeviceId --dart-define=API_BASE_URL=http://127.0.0.1:8080
} finally {
    Pop-Location
}
