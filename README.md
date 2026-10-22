# LeQuangHuy — Điểm danh sinh viên

## Luồng điểm danh sinh viên hiện tại

Sinh viên đăng ký khuôn mặt một lần trong tài khoản. Khi mở buổi học, ứng dụng đọc trạng thái điểm danh từ database. Nếu đã có bản ghi, màn hình chỉ hiện **Đã điểm danh**, thời gian và trạng thái. Nếu chưa có, sinh viên nhập mã 6 số, bấm **Quét khuôn mặt**, rồi mới có thể bấm **Xác nhận điểm danh**. Mã đúng một mình không mở khóa nút xác nhận.

Camera điểm danh dùng cùng `FacePreviewActivity`, mẫu `face_templates` theo UserId và hàm YuNet/SFace `face_auth.verify` như đăng nhập khuôn mặt. Quét thành công chỉ tạo chứng nhận xác thực có hạn 3 phút; chưa ghi Attendance. Khi bấm xác nhận, Android kiểm tra dịch vụ định vị, xin quyền nếu cần và lấy vị trí mới. API kiểm tra lại mã, chứng nhận khuôn mặt, tài khoản, vị trí và khoảng cách trước khi lưu. Nếu GPS tắt, ứng dụng yêu cầu bật và có nút mở cài đặt. Backend chặn lần ghi thứ hai bằng khóa `(session_id,user_id)` và trả `ALREADY_ATTENDED`.

Giảng viên chỉ bấm **Mở điểm danh**: ứng dụng lấy vị trí hiện tại, gửi `latitude`, `longitude`, `radiusM: 100`, rồi API lưu vào buổi học. Cả giảng viên và sinh viên dùng chung `LocationService`. Nếu dịch vụ định vị tắt hoặc quyền vị trí bị từ chối vĩnh viễn, ứng dụng mở màn hình cài đặt tương ứng và thử lấy vị trí lại khi quay về. Nên bật **Vị trí chính xác** cho ứng dụng; trong nhà, cần chờ GPS/mạng xác định vị trí hoặc ra nơi thoáng rồi thử lại.

API dùng cho luồng này: `GET /sessions/{id}/attendance/status`, `POST /sessions/{id}/code/validate`, `POST /sessions/{id}/face-verify`, `POST /sessions/{id}/checkin`. Vẫn chạy local; sau khi cập nhật mã cần khởi động lại backend và ứng dụng Android. Điện thoại thật phải truy cập được IP LAN của máy tính.

## Chạy API local

Máy cần Python 3.10+. Trong PowerShell tại thư mục gốc, cài thư viện nhận diện khuôn mặt local một lần:

```powershell
.\setup_face.ps1
```

Sau đó chạy backend bằng Python trong môi trường đã cài OpenCV:

```powershell
$env:BOOTSTRAP_ADMIN_EMAIL='admin@example.com'
$env:BOOTSTRAP_ADMIN_PASSWORD='choose-a-long-private-password'
.\run_backend.ps1
```

API dùng `backend/attendance.db` theo mặc định. Tài khoản admin chỉ được tạo **lần đầu** nếu database chưa có admin. Đổi các giá trị bằng biến môi trường trong [backend/.env.example](backend/.env.example). Không commit mật khẩu hoặc file `.env`.

Nếu chạy app trên điện thoại thật, đặt `$env:API_HOST='0.0.0.0'` trước khi chạy backend. Laptop và điện thoại phải cùng mạng LAN; cho phép cổng 8080 qua firewall nếu cần. Tìm IPv4 của laptop bằng `ipconfig`, rồi dùng địa chỉ đó trong lệnh Flutter. Không dùng `localhost` trên điện thoại để truy cập laptop.

Mặc định OTP được in ra cửa sổ backend để cả nhóm thử local. Muốn gửi email thật, đặt `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_FROM` trước khi khởi động. SMTP và hộp thư thật chưa được kiểm chứng trong môi trường này.

## Chạy Flutter

Máy cần Flutter SDK, Android SDK và thiết bị/emulator. Tại thư mục `mobile`:

```powershell
flutter pub get
flutter run
```

Mặc định app dùng `http://127.0.0.1:8080`, phù hợp với Android thật qua USB sau khi chạy `adb reverse tcp:8080 tcp:8080`. Có thể chạy nhanh từ thư mục gốc bằng `./run_android_usb.ps1` sau khi API đã chạy. Lệnh này kiểm tra API, ADB, bật reverse rồi chạy Flutter. Với Android emulator không dùng reverse, truyền `--dart-define=API_BASE_URL=http://10.0.2.2:8080`. Với điện thoại thật qua Wi-Fi:

```powershell
flutter run --dart-define=API_BASE_URL=http://192.168.1.10:8080
```

Thay IP ví dụ bằng IPv4 của laptop. Mọi lời gọi API đi qua [mobile/lib/api_config.dart](mobile/lib/api_config.dart). Sau này đổi sang HTTPS public chỉ cần đổi `API_BASE_URL`, đồng thời cấu hình lại backend, SMTP, CORS và Android network policy khi deploy.

## Luồng thử nhanh

1. Đăng ký hai tài khoản sinh viên qua email.
2. Đăng nhập admin và nhập OTP từ console API. Trong danh sách người dùng, đổi một tài khoản thành `teacher`.
3. Đăng nhập teacher, tạo lớp, đưa mã lớp cho student, bấm **Mở điểm danh** trên Android. Ứng dụng tự lấy vị trí giảng viên và đặt bán kính 100m.
4. Student tham gia lớp, mở buổi học, nhập mã, quét khuôn mặt, rồi bấm **Xác nhận điểm danh**. Luôn bật định vị và cấp quyền vị trí khi xác nhận. Giảng viên xem danh sách đã điểm danh.
5. Sau lần đăng nhập OTP đầu trên điện thoại, có thể chọn **Đăng nhập bằng sinh trắc học** để mở hộp thoại Android và dùng vân tay hoặc khuôn mặt mà hệ điều hành hỗ trợ. Phiên API đã lưu hết hạn sau 7 ngày.
6. Tùy chọn **Quét khuôn mặt đã đăng ký trong app** là cơ chế riêng: sau khi đăng nhập bằng OTP, trong trang chính chọn **Đăng ký khuôn mặt** để lưu ba mẫu đặc trưng vào SQLite. Một khuôn mặt có thể đăng ký cho nhiều tài khoản; mỗi tài khoản giữ mẫu theo UserId riêng. Đăng xuất, nhập username hoặc email của tài khoản muốn đăng nhập rồi chọn nút quét riêng. App lấy ảnh khi camera đang mở, kiểm tra nhìn thẳng và quay đầu rồi so khớp với mẫu của tài khoản đã nhập trên backend local. Ảnh gốc được xử lý trong bộ nhớ, chỉ đặc trưng được lưu. Trang chính có nút xóa mẫu.
7. Bước quay đầu của cơ chế riêng giảm khả năng dùng một ảnh tĩnh, nhưng không chống được mọi video hoặc kỹ thuật giả mạo. Chức năng này chỉ dành cho bài tập/local; trước khi dùng thật cần kiểm thử độ chính xác, chống giả mạo và HTTPS. Mô hình YuNet/SFace nằm trong `backend/models` cùng giấy phép; OpenCV xử lý trên laptop, không dùng dịch vụ online.
8. Dashboard sinh viên hiển thị tỉ lệ chuyên cần và cảnh báo khi dưới 80% sau ít nhất ba buổi đã kết thúc.

## Kiểm tra

```powershell
cd backend
python -m unittest -v test_api.py
cd ../mobile
dart analyze lib
flutter build apk --debug --dart-define=API_BASE_URL=http://192.168.1.10:8080
```

Chỉ đưa IP LAN vào APK thử trên điện thoại thật; Android emulator dùng mặc định. SQLite, mã OTP console và HTTP LAN chỉ dành cho giai đoạn local. Cần SMTP thực, HTTPS, giới hạn CORS, bảo vệ endpoint khỏi lạm dụng và kiểm tra sinh trắc học/GPS trên thiết bị thật trước khi phát hành.
