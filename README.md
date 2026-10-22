# LeQuangHuy – ứng dụng điểm danh sinh viên

> Hướng dẫn triển khai VPS và OTP email hiện tại: [DEPLOY.md](DEPLOY.md). App dùng API Python/SQLite ở `LeQuangHuyBackend/`; Flutter mặc định gọi `http://103.131.85.188:8080`. Đăng ký cần xác minh email trước khi tài khoản được tạo. Các hướng dẫn local bên dưới có thể dùng `--dart-define=API_BASE_URL=...` để ghi đè URL.

Hướng dẫn cho máy Windows vừa clone repository. **Flutter hiện gọi API Python/SQLite ở cổng 8080.** Thư mục `LeQuangHuyApi/` là API ASP.NET Core tùy chọn, không cần chạy để dùng đăng nhập hay điểm danh hiện tại. Project không dùng SQL Server, Entity Framework migration hoặc Swagger.

## 1. Yêu cầu môi trường

| Thành phần | Phiên bản/công dụng |
| --- | --- |
| Git | Clone source. |
| Python | 3.10 trở lên, có `venv` và `pip`; máy phát triển hiện dùng 3.14.5. |
| Flutter và Dart | `pubspec.yaml` yêu cầu Dart `>=3.5.0 <4.0.0`; máy phát triển dùng Flutter 3.47.5 và Dart 3.13.4. Flutter đã kèm Dart. |
| Android Studio hoặc VS Code | Cài Android SDK, emulator, Android SDK Platform-Tools (`adb`). Chạy `flutter doctor --android-licenses`. |
| JDK | 17. Android project dùng Gradle wrapper 9.3.1, Android Gradle Plugin 9.1.0 và Kotlin plugin 2.4.0. |
| .NET SDK | Chỉ cần nếu chạy `LeQuangHuyApi/` tùy chọn: .NET 10 (`net10.0`). |

Không cần SQL Server/SSMS hoặc .NET SDK để chạy app chính. Flutter không dùng package `geolocator`/`location`; Camera, GPS và sinh trắc học được gọi qua Android native code.

Khi đưa thay đổi lên GitHub, cần bao gồm `LeQuangHuyFrontend/android/gradlew`, `gradlew.bat` và `gradle/wrapper/gradle-wrapper.jar` cùng `gradle-wrapper.properties`; bản clone mới cần đủ bốn file Gradle wrapper này.

## 2. Clone project

URL dưới đây lấy từ Git `origin` của source hiện tại. Nếu nhóm chuyển repository, thay bằng URL GitHub mới.

```powershell
git clone https://github.com/lqh02468/BaiTapLTDD.git
cd BaiTapLTDD
```

Các lệnh dưới đây giả định đang ở thư mục gốc vừa clone. Không cần đường dẫn `D:\...` hoặc IP của máy Huy.

## 3. Cấu trúc project

```text
BaiTapLTDD/
├── LeQuangHuyFrontend/                  Flutter app; lib/api_config.dart quản lý API_BASE_URL
│   └── android/             Camera, GPS, sinh trắc học native và Gradle wrapper
├── LeQuangHuyBackend/                 API Python chính, SQLite, test_api.py
│   ├── models/              YuNet/SFace .onnx và giấy phép, có trong Git
│   └── .env.example         Mẫu biến môi trường; không tự được nạp
├── LeQuangHuyApi/                ASP.NET Core 10 API khuôn mặt tùy chọn
├── setup_face.ps1           Tạo Python venv, cài OpenCV/numpy
├── run_backend.ps1          Chạy API Python
├── run_android_usb.ps1      Kiểm tra API, adb reverse và chạy Flutter
└── README.md
```

## 4. Cài và chạy backend chính

Trong PowerShell ở thư mục gốc:

```powershell
python --version
.\setup_face.ps1
$env:API_HOST = '127.0.0.1'
$env:API_PORT = '8080'
$env:BOOTSTRAP_ADMIN_EMAIL = 'admin@example.com'
$env:BOOTSTRAP_ADMIN_PASSWORD = '<mat-khau-rieng-it-nhat-10-ky-tu>'
.\run_backend.ps1
```

Thay email/mật khẩu ví dụ bằng giá trị của **bạn**. `setup_face.ps1` tạo `.tool/face_venv/` và cài `opencv-python-headless==4.11.0.86` cùng NumPy; chỉ cần chạy lại khi cài mới hoặc đổi Python. Nếu PowerShell chặn script, chạy `Set-ExecutionPolicy -Scope Process Bypass` trong chính cửa sổ đó rồi thử lại. Giữ cửa sổ backend mở khi dùng app.

API mặc định ở `http://127.0.0.1:8080`. Mở `http://127.0.0.1:8080/health`; phải nhận JSON `{"status":"ok"}`. **Không có Swagger**: `/swagger` trả 404. Nếu đổi `API_PORT`, phải dùng cùng cổng trong URL Flutter. Script USB hiện dùng cổng 8080.

### Database và cấu hình

API chính dùng **SQLite** tại `LeQuangHuyBackend/attendance.db` theo mặc định. `server.py` tự tạo database và bảng khi khởi động; không có lệnh migration hoặc connection string SQL Server. File `.db` không đưa lên Git. Nếu muốn dùng file khác, đặt biến `ATTENDANCE_DB` thành **đường dẫn tuyệt đối trên máy bạn** trước khi chạy backend. Mỗi người clone sẽ có database và tài khoản riêng.

`LeQuangHuyBackend/.env.example` chỉ liệt kê tên biến; script hiện đọc **biến môi trường PowerShell**, không tự nạp file `.env`. Các biến chính là `API_HOST`, `API_PORT`, `ATTENDANCE_DB`, `BOOTSTRAP_ADMIN_EMAIL`, `BOOTSTRAP_ADMIN_PASSWORD`, `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_FROM`, `CORS_ORIGIN`. Không commit mật khẩu, token hay database thật. Admin được tạo khi database chưa có admin và đã đặt email/mật khẩu bootstrap; đổi biến sau đó không đổi mật khẩu tài khoản admin đã tạo.

## 5. Email OTP và tài khoản thử

Chế độ Production bắt buộc cấu hình SMTP để gửi OTP thật. Chỉ khi `APP_ENV=Development` và thiếu SMTP, OTP mới in trong cửa sổ backend để debug. Để dùng SMTP, đặt biến riêng trong cùng PowerShell **trước khi chạy backend**:

```powershell
$env:SMTP_HOST = '<smtp-host>'
$env:SMTP_PORT = '587'
$env:SMTP_USER = '<smtp-user>'
$env:SMTP_PASSWORD = '<smtp-secret>'
$env:SMTP_FROM = '<email-nguoi-gui>'
```

Backend dùng SMTP với STARTTLS. Project không cung cấp secret; không đưa giá trị thật lên GitHub. Không có tài khoản giảng viên/sinh viên demo được seed. Hãy đăng ký tài khoản mới trong app và xác minh OTP gửi đến email trước khi đăng nhập. Tài khoản có username `admin` và role `admin` đăng nhập bằng mật khẩu, không cần OTP; sau đó đổi role một tài khoản thành `teacher` trong màn hình quản lý. Tài khoản mới mặc định là `student`.

## 6. Chạy Flutter và chọn API Base URL

Mở PowerShell **khác**, ở thư mục gốc:

```powershell
cd LeQuangHuyFrontend
flutter pub get
flutter doctor
flutter devices
```

Mọi màn hình dùng chung `LeQuangHuyFrontend/lib/api_config.dart` với `String.fromEnvironment('API_BASE_URL')`. **Không sửa URL trong từng màn hình.** Truyền URL khi chạy/build bằng `--dart-define=API_BASE_URL=...`. Mặc định là `http://103.131.85.188:8080`; dùng URL local qua `--dart-define` khi phát triển. Sau khi đổi `--dart-define`, chạy lại app; hot reload không đổi giá trị này.

### Android Emulator

Chạy backend với `API_HOST=127.0.0.1`, mở emulator, rồi trong `LeQuangHuyFrontend/` chạy:

```powershell
flutter run --dart-define=API_BASE_URL=http://10.0.2.2:8080
```

`10.0.2.2` là địa chỉ laptop từ Android Emulator. Camera/sinh trắc học tùy khả năng emulator; nên dùng điện thoại thật để thử nhận diện khuôn mặt và GPS.

### Điện thoại Android cắm USB

Bật Developer options, USB debugging và chấp nhận khóa RSA trên điện thoại. Chạy backend tại `127.0.0.1:8080`. Từ **thư mục gốc** chạy:

```powershell
adb devices
.\run_android_usb.ps1
```

Script tìm `adb` trong `PATH` hoặc `ANDROID_HOME`/`ANDROID_SDK_ROOT`, kiểm tra `/health`, chạy `adb reverse tcp:8080 tcp:8080` rồi chạy Flutter với `API_BASE_URL=http://127.0.0.1:8080`. **USB không cần sửa IP hay cùng Wi-Fi.** Nếu có nhiều thiết bị: `.\run_android_usb.ps1 -DeviceId <id-tu-adb-devices>`.

Nếu PowerShell không nhận lệnh `adb`, tìm Android SDK path trong Android Studio → SDK Manager, rồi thêm thư mục `platform-tools` vào `PATH` hoặc đặt `ANDROID_HOME` tới thư mục SDK đó trên máy bạn.

### Điện thoại Android qua Wi-Fi/LAN

Laptop và điện thoại phải cùng mạng và nhìn thấy nhau. Trong cửa sổ backend, đặt host **trước khi chạy**:

```powershell
$env:API_HOST = '0.0.0.0'
$env:API_PORT = '8080'
.\run_backend.ps1
```

Trên laptop chạy `ipconfig`, lấy **IPv4 của card Wi-Fi đang dùng**. Ví dụ nếu laptop **của bạn** là `192.168.1.10`, trong `LeQuangHuyFrontend/` chạy:

```powershell
flutter devices
flutter run --dart-define=API_BASE_URL=http://192.168.1.10:8080
```

**Thay `192.168.1.10` bằng IPv4 thật của máy đang chạy backend.** Mỗi thành viên chỉ cần thay IP trong **lệnh `flutter run` hoặc `flutter build`**; không sửa file Dart và không dùng IP cố định của máy Huy. Khi chuyển mạng/IP thay đổi, chạy lại Flutter với URL mới. Kiểm tra `http://<IP-cua-ban>:8080/health` trong trình duyệt điện thoại trước nếu app bị timeout.

Windows Firewall có thể chặn cổng 8080. Chỉ cho phép Python hoặc TCP 8080 trên mạng **Private** trong Windows Defender Firewall; không tắt toàn bộ firewall. Wi-Fi công cộng có client isolation có thể không cho hai thiết bị kết nối; dùng USB `adb reverse` khi đó.

## 7. Android permissions và khuôn mặt

Lần đầu chạy, cấp **Camera** khi đăng ký/đăng nhập/quét mặt và **Location** khi giảng viên mở buổi hoặc sinh viên xác nhận. Bật GPS/Location Service, nên chọn **Vị trí chính xác**. Sinh trắc học phải thiết lập sẵn trong Android; app dùng prompt của hệ điều hành. Không cần quyền vị trí nền.

Đăng nhập OTP trước, vào tài khoản và **đăng ký khuôn mặt**. Mẫu đó dùng chung để đăng nhập bằng mặt và xác thực điểm danh. Backend dùng `LeQuangHuyBackend/models/yunet.onnx` để phát hiện mặt và `LeQuangHuyBackend/models/sface_int8.onnx` để tạo/so khớp đặc trưng. Hai file ONNX và giấy phép đã có trong Git; **không cần `.tflite` hay tải model riêng**. Một mặt có thể đăng ký cho nhiều tài khoản thử nhưng mẫu lưu theo UserId. Quét mặt điểm danh chỉ mở khóa nút xác nhận; khi xác nhận app còn lấy GPS, API kiểm tra bán kính 100 m.

## 8. Thứ tự chạy và kiểm tra nhanh

1. Clone; cài Python, Flutter, Android SDK/JDK; chạy `.\setup_face.ps1` và `flutter pub get` lần đầu.
2. Đặt email/mật khẩu bootstrap rồi chạy `.\run_backend.ps1`.
3. Mở `http://127.0.0.1:8080/health`; thấy `{"status":"ok"}` rồi mới chạy Flutter. API chính không có Swagger.
4. Kết nối emulator/điện thoại, chọn URL API theo mục 6, chạy Flutter.
5. Cấp Camera/Location, đăng ký/đăng nhập và lấy OTP từ email qua SMTP đã cấu hình (hoặc console chỉ trong Development).
6. Admin đổi role giảng viên; giảng viên tạo lớp/mở buổi; sinh viên tham gia lớp, đăng ký mặt, nhập mã, quét mặt và xác nhận khi GPS bật.

## 9. ASP.NET Core `LeQuangHuyApi/` (tùy chọn)

Phần này **không thay thế API Python cổng 8080** và app Flutter hiện không gọi nó. Nếu cần thử, cài .NET SDK 10, chạy API Python trước để tạo SQLite, rồi dùng PowerShell khác:

```powershell
cd LeQuangHuyApi
dotnet restore
dotnet build --no-restore
dotnet run --no-restore --urls http://127.0.0.1:8081
```

Kiểm tra `http://127.0.0.1:8081/health`. API .NET dùng `Microsoft.Data.Sqlite` 10.0.2, cùng `LeQuangHuyBackend/attendance.db` mặc định hoặc `ATTENDANCE_DB` giống API Python, tự tạo `face_profiles`. **Không dùng SQL Server, `appsettings.json` connection string, `dotnet ef database update` hay Swagger.** Không cần chạy `run_face_api.ps1` để app chính hoạt động.

## 10. Kiểm tra build

```powershell
cd LeQuangHuyBackend
..\.tool\face_venv\Scripts\python.exe -m py_compile server.py face_auth.py
..\.tool\face_venv\Scripts\python.exe -m unittest -v test_api.py
cd ..\LeQuangHuyFrontend
flutter analyze
flutter build apk --debug --dart-define=API_BASE_URL=http://10.0.2.2:8080
```

Build trên nhúng URL **emulator**. Nếu build APK cho Wi-Fi, thay bằng IPv4 thật của laptop. Với USB, dùng `http://127.0.0.1:8080` cùng `adb reverse`. APK debug nằm ở `LeQuangHuyFrontend/build/app/outputs/flutter-apk/app-debug.apk` khi build thành công.

## 11. Lỗi thường gặp

| Hiện tượng | Cách kiểm tra |
| --- | --- |
| Flutter không gọi được API / `TimeoutException` | Kiểm tra `/health`, cổng 8080, `API_HOST`, URL trong `--dart-define`. Emulator dùng `10.0.2.2`; USB dùng `adb reverse`; Wi-Fi dùng IPv4 laptop và cùng mạng. Kiểm tra Firewall. |
| Điện thoại không hiện trong `flutter devices` | Bật USB debugging, cáp truyền dữ liệu, chấp nhận RSA, kiểm tra `adb devices` và driver USB Android. |
| Camera không mở | Cấp Camera permission, đóng app khác đang dùng camera, dùng thiết bị có camera trước. |
| GPS/vị trí lỗi | Bật Location Service, cấp Location permission và Vị trí chính xác trong App Settings; ra nơi thoáng nếu tín hiệu yếu. App phân biệt GPS tắt, từ chối quyền, từ chối vĩnh viễn và timeout. |
| SQLite lỗi | Kiểm tra quyền ghi thư mục `LeQuangHuyBackend/` và `ATTENDANCE_DB` nếu tự đặt. Không cần SQL Server. |
| Không nhận OTP email | Nếu chưa cấu hình SMTP, xem dòng `[LOCAL OTP]` ở terminal backend. Nếu dùng SMTP, kiểm tra host, port, STARTTLS, tài khoản và secret riêng. |
| Flutter/Gradle build lỗi | Chạy `flutter doctor -v`, `flutter pub get`, kiểm tra JDK 17, Android SDK/licenses và Gradle wrapper trong `LeQuangHuyFrontend/android/gradle/wrapper/`. Nếu lỗi tại `settings.gradle.kts` trước khi biên dịch app, gửi log Gradle đầy đủ cho nhóm. |

Project đang ưu tiên chạy local, chưa cần deploy.
