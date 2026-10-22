# Deploy ứng dụng điểm danh lên Ubuntu VPS

## Kiến trúc source hiện tại

Flutter trong `LeQuangHuyFrontend/` gọi **API Python** ở `LeQuangHuyBackend/server.py`. API này quản lý tài khoản, OTP, khuôn mặt, lớp, phiên và điểm danh; nó dùng SQLite. `LeQuangHuyApi/` là ASP.NET Core **.NET 10** API khuôn mặt phụ, dùng `Microsoft.Data.Sqlite`, không được Flutter gọi và không có Entity Framework migration. Vì vậy chạy `dotnet publish` riêng cho `LeQuangHuyApi/` sẽ **không** thay thế API chính. Hướng dẫn dưới đây triển khai API chính để điện thoại dùng đủ chức năng. Không chạy cả hai trên port 8080.

## 1. Chuẩn bị VPS

Trước khi `git clone` trên VPS, đưa các thay đổi source và file `deploy/` trong workspace này lên repository (commit/push theo quy trình của bạn). Source chưa push sẽ không xuất hiện trong bản clone. Giữ `attendance-backup.db` và mọi file secret ngoài Git.

Đăng nhập SSH vào VPS Ubuntu. Cài Git, Python 3, venv, SQLite CLI và công cụ kiểm tra:

```bash
sudo apt update
sudo apt install -y git python3 python3-venv python3-pip sqlite3 curl
sudo useradd --system --home /var/lib/lequanghuy --shell /usr/sbin/nologin lequanghuy
sudo install -d -o lequanghuy -g lequanghuy -m 750 /var/lib/lequanghuy
sudo git clone https://github.com/lqh02468/BaiTapLTDD.git /opt/lequanghuy
cd /opt/lequanghuy
sudo python3 -m venv .venv
sudo .venv/bin/pip install -r LeQuangHuyBackend/requirements-face.txt
sudo chown -R root:root /opt/lequanghuy
sudo chmod -R a+rX /opt/lequanghuy
```

Nếu user/service đã tồn tại thì bỏ qua lệnh tạo tương ứng. Kiểm tra bản Ubuntu/Python và dung lượng RAM; OpenCV cần thư viện hệ thống và đủ RAM. Nếu `import cv2` lỗi vì thiếu `libGL.so.1`, cài `libgl1`.

`dotnet restore LeQuangHuyApi/LeQuangHuyApi.csproj` và `dotnet publish LeQuangHuyApi/LeQuangHuyApi.csproj -c Release` chỉ build API phụ. Không cần chạy chúng để deploy app chính. Source không dùng SQL Server hoặc PostgreSQL nên không có lệnh EF migration.

## 2. Chuyển database lên VPS

API mặc định dùng `LeQuangHuyBackend/attendance.db` trên laptop. Để giữ tài khoản, FaceEmbedding/mẫu khuôn mặt, lớp và điểm danh, tạo **snapshot SQLite** trong lúc backend local đã dừng:

```bash
python LeQuangHuyBackend/backup_db.py attendance-backup.db
scp attendance-backup.db <ssh-user>@103.131.85.188:/tmp/attendance-backup.db
```

Hai lệnh trên chạy ở máy chứa database cũ. Script dùng SQLite backup API và kiểm tra integrity; `attendance-backup.db` không nên commit lên Git. Trên VPS:

```bash
sudo install -o lequanghuy -g lequanghuy -m 600 /tmp/attendance-backup.db /var/lib/lequanghuy/attendance.db
sudo -u lequanghuy sqlite3 /var/lib/lequanghuy/attendance.db 'PRAGMA integrity_check;'
```

Kết quả integrity phải là `ok`. Nếu không cần dữ liệu cũ, bỏ qua copy: API tự tạo SQLite mới ở đường dẫn `ATTENDANCE_DB` khi chạy. Khi nâng cấp, `init_db()` tự thêm cột OTP mới và bảng đăng ký chờ xác minh; không có EF migration. **Không copy file `.db` đang được ghi trực tiếp** vì có thể bỏ sót WAL và làm hỏng dữ liệu.

## 3. Cấu hình secrets và SMTP

Tạo `/etc/lequanghuy-api.env` trên VPS theo `LeQuangHuyBackend/.env.example`, thay toàn bộ giá trị rỗng bằng giá trị thật. File này nằm ngoài Git:

```bash
sudo install -o root -g root -m 600 /dev/null /etc/lequanghuy-api.env
sudo nano /etc/lequanghuy-api.env
```

Các biến cần có:

```text
APP_ENV=Production
API_HOST=0.0.0.0
API_PORT=8080
ATTENDANCE_DB=/var/lib/lequanghuy/attendance.db
BOOTSTRAP_ADMIN_EMAIL=<email-admin>
BOOTSTRAP_ADMIN_PASSWORD=<mat-khau-manh>
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=<gmail-gui>
SMTP_PASSWORD=<gmail-app-password>
SMTP_FROM=<gmail-gui>
CORS_ORIGINS=
```

Với Gmail, `SMTP_PASSWORD` là **App Password**, không phải mật khẩu Gmail thường. Nếu provider khác, đổi host/port/tài khoản tương ứng và bảo đảm hỗ trợ STARTTLS. Tài khoản `admin` có role `admin` đăng nhập trực tiếp bằng mật khẩu, không cần OTP; tài khoản giảng viên/sinh viên vẫn cần SMTP để nhận OTP. API sẽ từ chối gửi OTP nếu SMTP thiếu trong Production; không in OTP ra log. `BOOTSTRAP_ADMIN_*` chỉ tạo admin khi database chưa có admin. API hiện dùng token ngẫu nhiên lưu dạng hash trong SQLite, **không dùng JWT** nên không có `Jwt__Key`.

Android native không bị CORS. Nếu sau này có web frontend, đặt `CORS_ORIGINS=https://ten-mien-web` (nhiều origin cách nhau bằng dấu phẩy); không đặt `*`.

## 4. Cài và chạy lâu dài với systemd

```bash
sudo cp /opt/lequanghuy/deploy/LeQuangHuyApi.service /etc/systemd/system/LeQuangHuyApi.service
sudo systemctl daemon-reload
sudo systemctl enable --now LeQuangHuyApi
sudo systemctl status LeQuangHuyApi --no-pager
sudo journalctl -u LeQuangHuyApi -n 80 --no-pager
```

Service tự chạy sau reboot, tự khởi động lại khi lỗi, đọc secrets từ `/etc/lequanghuy-api.env` và listen `0.0.0.0:8080`. Cập nhật source bằng `git pull` trong `/opt/lequanghuy`, cài lại dependencies nếu thay requirements, rồi `sudo systemctl restart LeQuangHuyApi`.

Nếu VPS đã chạy unit cũ `lequanghuy-api.service`, chuyển sang tên mới sau khi push commit đổi tên thư mục lên GitHub:

```bash
sudo systemctl disable --now lequanghuy-api.service
sudo git -C /opt/lequanghuy pull --ff-only origin main
sudo cp /opt/lequanghuy/deploy/LeQuangHuyApi.service /etc/systemd/system/LeQuangHuyApi.service
sudo systemctl daemon-reload
sudo systemctl enable --now LeQuangHuyApi.service
sudo systemctl status LeQuangHuyApi.service --no-pager
```

Giữ `/etc/lequanghuy-api.env` hiện có để không phải di chuyển file secret. `ATTENDANCE_DB=/var/lib/lequanghuy/attendance.db` cũng giữ nguyên để dùng database hiện tại.

## 5. Firewall và kiểm tra Internet

```bash
sudo ufw allow 8080/tcp
sudo ufw status
curl -f http://127.0.0.1:8080/health
curl -f http://103.131.85.188:8080/health
curl -i http://103.131.85.188:8080/health/face
```

`/health/face` trả `200` khi OpenCV và hai mô hình khuôn mặt tải được. VPS hiện tại không hỗ trợ tập lệnh CPU `X86_V2` mà NumPy 2.4+ yêu cầu; `requirements-face.txt` đã khóa NumPy 2.3.5. Nếu trả `503`, cài lại thư viện bằng đúng Python mà service đang chạy, rồi khởi động lại:

```bash
sudo /opt/lequanghuy/.venv/bin/python -m pip install --no-cache-dir -r /opt/lequanghuy/LeQuangHuyBackend/requirements-face.txt
sudo systemctl restart LeQuangHuyApi.service
curl -i http://127.0.0.1:8080/health/face
```

Nếu VPS có firewall của nhà cung cấp, mở inbound TCP 8080 tại đó. Từ **máy khác mạng VPS** chạy `curl -f http://103.131.85.188:8080/health`; phải thấy `{"status":"ok"}`. API chính không có Swagger; `/swagger` trả 404. Sau này nên dùng domain và HTTPS, rồi đổi `API_BASE_URL` khi build Flutter.

## 6. Kiểm tra OTP thật và app

Từ app Android, đăng ký với email thật. `POST /auth/register` gửi OTP đến email đó; nhập mã trong app sẽ gọi `/auth/register/verify`. Giảng viên/sinh viên đăng nhập bằng username/password sẽ nhận mã vào **email tài khoản trong database**, sau đó `/auth/verify` cấp token. Tài khoản username `admin` có role `admin` nhận token ngay sau khi nhập đúng mật khẩu. Kiểm tra sai mã, mã quá 5 phút, dùng lại, gửi mã mới và giới hạn 60 giây. Kiểm tra hộp thư Spam nếu email chưa đến; xem log service nhưng không có OTP production. Đừng dùng tài khoản email của người khác để thử.

Chạy trên điện thoại thật (có Internet, không cần cùng Wi-Fi/laptop):

```bash
cd LeQuangHuyFrontend
flutter pub get
flutter run --dart-define=API_BASE_URL=http://103.131.85.188:8080
```

Android đã cho phép cleartext HTTP tạm thời. Khi có domain/HTTPS, đổi duy nhất `API_BASE_URL=https://api.example.com` lúc chạy/build lại. Sau khi deploy và SMTP hoạt động, thử đủ vai trò admin, giảng viên, sinh viên; CRUD lớp, face login/enroll, biometric, GPS mở điểm danh 100m, xác nhận sinh viên, chống trùng và trạng thái đã điểm danh. Các bước này cần điện thoại thật và VPS hoạt động.
