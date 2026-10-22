"""Local attendance API. Face sign-in additionally uses OpenCV."""
import base64
import hashlib
import hmac
import json
import os
import secrets
import smtplib
import sqlite3
import time
from contextlib import contextmanager
from email.message import EmailMessage
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from math import isfinite
from urllib.parse import urlparse, parse_qs

import face_auth

DB_PATH = Path(os.getenv('ATTENDANCE_DB', Path(__file__).with_name('attendance.db')))
HOST = os.getenv('API_HOST', '127.0.0.1')
PORT = int(os.getenv('API_PORT', '8080'))
OTP_MINUTES = 10


@contextmanager
def connect():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(DB_PATH, timeout=10)
    db.row_factory = sqlite3.Row
    db.execute('PRAGMA foreign_keys=ON')
    try:
        with db:
            yield db
    finally:
        db.close()


def init_db():
    with connect() as db:
        db.executescript('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY, username TEXT NOT NULL UNIQUE, email TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL, role TEXT NOT NULL DEFAULT 'student',
            created_at INTEGER NOT NULL, student_code TEXT);
        CREATE TABLE IF NOT EXISTS otps (
            id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id),
            code_hash TEXT NOT NULL, expires_at INTEGER NOT NULL, attempts INTEGER NOT NULL DEFAULT 0,
            used INTEGER NOT NULL DEFAULT 0);
        CREATE TABLE IF NOT EXISTS tokens (
            token_hash TEXT PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id),
            expires_at INTEGER NOT NULL);
        CREATE TABLE IF NOT EXISTS face_templates (
            user_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
            features TEXT NOT NULL, updated_at INTEGER NOT NULL);
        CREATE TABLE IF NOT EXISTS face_attempts (
            identifier TEXT PRIMARY KEY, attempts INTEGER NOT NULL, window_start INTEGER NOT NULL);
        CREATE TABLE IF NOT EXISTS classes (
            id INTEGER PRIMARY KEY, name TEXT NOT NULL, room TEXT NOT NULL DEFAULT '',
            teacher_id INTEGER NOT NULL REFERENCES users(id), join_code TEXT NOT NULL UNIQUE,
            created_at INTEGER NOT NULL);
        CREATE TABLE IF NOT EXISTS enrollments (
            class_id INTEGER NOT NULL REFERENCES classes(id) ON DELETE CASCADE,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            PRIMARY KEY(class_id,user_id));
        CREATE TABLE IF NOT EXISTS sessions (
            id INTEGER PRIMARY KEY, class_id INTEGER NOT NULL REFERENCES classes(id) ON DELETE CASCADE,
            starts_at INTEGER NOT NULL, ends_at INTEGER NOT NULL, code TEXT NOT NULL,
            latitude REAL, longitude REAL, radius_m REAL,
            created_at INTEGER NOT NULL);
        CREATE TABLE IF NOT EXISTS face_checkin_proofs (
            proof_hash TEXT PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            session_id INTEGER NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
            code_hash TEXT NOT NULL, expires_at INTEGER NOT NULL);
        CREATE TABLE IF NOT EXISTS attendance (
            session_id INTEGER NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
            user_id INTEGER NOT NULL REFERENCES users(id), checked_at INTEGER NOT NULL,
            latitude REAL, longitude REAL, method TEXT NOT NULL,
            PRIMARY KEY(session_id,user_id));
        ''')
        columns = {row['name'] for row in db.execute('PRAGMA table_info(users)')}
        if 'student_code' not in columns:
            db.execute('ALTER TABLE users ADD COLUMN student_code TEXT')
        db.execute("UPDATE users SET student_code=printf('SV%06d',id) WHERE student_code IS NULL")
        admin_email = os.getenv('BOOTSTRAP_ADMIN_EMAIL', '').strip().lower()
        admin_password = os.getenv('BOOTSTRAP_ADMIN_PASSWORD', '')
        if admin_email and len(admin_password) >= 10 and not db.execute('SELECT 1 FROM users WHERE role="admin"').fetchone():
            uid = db.execute('INSERT INTO users(username,email,password_hash,role,created_at) VALUES(?,?,?,?,?)',
                             ('admin', admin_email, password_hash(admin_password), 'admin', int(time.time()))).lastrowid
            db.execute('UPDATE users SET student_code=? WHERE id=?', (f'SV{uid:06d}', uid))


def password_hash(password):
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac('sha256', password.encode(), salt, 260000)
    return base64.b64encode(salt + digest).decode()


def password_ok(password, encoded):
    try:
        raw = base64.b64decode(encoded)
        result = hashlib.pbkdf2_hmac('sha256', password.encode(), raw[:16], 260000)
        return hmac.compare_digest(raw[16:], result)
    except (ValueError, TypeError):
        return False


def verify_registered_face(db, user, images, mismatch_message):
    """Use the same per-user templates and SFace verification for login and check-in."""
    template = db.execute('SELECT features FROM face_templates WHERE user_id=?',
                          (user['id'],)).fetchone() if user else None
    require(template, 401, 'Tài khoản chưa đăng ký khuôn mặt hoặc không tồn tại')
    try:
        face_auth.verify(images, json.loads(template['features']))
    except face_auth.FaceError:
        raise ApiError(401, mismatch_message)


def send_otp(address, code):
    host = os.getenv('SMTP_HOST')
    if not host:
        print(f'[LOCAL OTP] {address}: {code}', flush=True)
        return 'console'
    message = EmailMessage()
    message['Subject'] = 'Ma OTP dang nhap LeQuangHuy'
    message['From'] = os.getenv('SMTP_FROM', os.getenv('SMTP_USER', ''))
    message['To'] = address
    message.set_content(f'Ma OTP cua ban la {code}. Hieu luc {OTP_MINUTES} phut.')
    with smtplib.SMTP(host, int(os.getenv('SMTP_PORT', '587')), timeout=15) as smtp:
        smtp.starttls()
        smtp.login(os.getenv('SMTP_USER', ''), os.getenv('SMTP_PASSWORD', ''))
        smtp.send_message(message)
    return 'email'


def distance_m(a, b, c, d):
    from math import radians, sin, cos, asin, sqrt
    x = radians(float(c) - float(a))
    y = radians(float(d) - float(b))
    z = sin(x/2)**2 + cos(radians(float(a))) * cos(radians(float(c))) * sin(y/2)**2
    return 12742000 * asin(sqrt(min(1.0, z)))


def valid_coordinates(lat, lon):
    try:
        latitude, longitude = float(lat), float(lon)
        return isfinite(latitude) and isfinite(longitude) and -90 <= latitude <= 90 and -180 <= longitude <= 180
    except (TypeError, ValueError):
        return False


class ApiError(Exception):
    def __init__(self, status, message, code=None):
        self.status, self.message, self.code = status, message, code


def require(condition, status, message):
    if not condition:
        raise ApiError(status, message)


class Handler(BaseHTTPRequestHandler):
    def send_json(self, status, data):
        payload = json.dumps(data, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(payload)))
        self.send_header('Access-Control-Allow-Origin', os.getenv('CORS_ORIGIN', '*'))
        self.send_header('Access-Control-Allow-Headers', 'Content-Type, Authorization')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, PUT, DELETE, OPTIONS')
        self.end_headers()
        self.wfile.write(payload)

    def do_OPTIONS(self):
        self.send_json(200, {})

    def do_GET(self): self.handle_request('GET')
    def do_POST(self): self.handle_request('POST')
    def do_PUT(self): self.handle_request('PUT')
    def do_DELETE(self): self.handle_request('DELETE')

    def handle_request(self, method):
        try:
            parsed = urlparse(self.path)
            path = parsed.path.rstrip('/') or '/'
            length = int(self.headers.get('Content-Length', '0'))
            face_verify = path.startswith('/sessions/') and path.endswith('/face-verify')
            limit = 1100000 if face_verify or path in ('/auth/face/login', '/me/face/enroll', '/face/analyze') else 65536
            require(0 <= length <= limit, 413, 'Dữ liệu quá lớn')
            body = json.loads(self.rfile.read(length)) if length else {}
            require(isinstance(body, dict), 400, 'JSON không hợp lệ')
            with connect() as db:
                status, result = self.route(db, method, path, body, parse_qs(parsed.query))
            self.send_json(status, result)
        except ApiError as e:
            payload = {'error': e.message}
            if e.code: payload['code'] = e.code
            self.send_json(e.status, payload)
        except face_auth.FaceError as e:
            self.send_json(400, {'error': str(e)})
        except (ValueError, TypeError, json.JSONDecodeError):
            self.send_json(400, {'error': 'Dữ liệu không hợp lệ'})
        except sqlite3.IntegrityError:
            self.send_json(409, {'error': 'Dữ liệu đã tồn tại hoặc không hợp lệ'})
        except Exception as e:
            print('API error:', repr(e), flush=True)
            self.send_json(500, {'error': 'Lỗi máy chủ'})

    def actor(self, db):
        bearer = self.headers.get('Authorization', '')
        require(bearer.startswith('Bearer '), 401, 'Cần đăng nhập')
        token_hash = hashlib.sha256(bearer[7:].encode()).hexdigest()
        user = db.execute('SELECT users.id,username,email,role,student_code FROM tokens JOIN users ON users.id=tokens.user_id WHERE token_hash=? AND expires_at>?',
                          (token_hash, int(time.time()))).fetchone()
        require(user, 401, 'Phiên đăng nhập hết hạn')
        return dict(user)

    def route(self, db, method, path, body, query):
        now = int(time.time())
        if method == 'GET' and path == '/health':
            return 200, {'status': 'ok'}
        if method == 'POST' and path == '/auth/register':
            username = str(body.get('username', '')).strip()
            email = str(body.get('email', '')).strip().lower()
            password = str(body.get('password', ''))
            require(3 <= len(username) <= 40 and username.replace('_', '').isalnum(), 400, 'Username cần 3-40 ký tự chữ/số')
            require('@' in email and '.' in email.split('@')[-1] and len(email) <= 254, 400, 'Email không hợp lệ')
            require(len(password) >= 8, 400, 'Mật khẩu cần ít nhất 8 ký tự')
            uid = db.execute('INSERT INTO users(username,email,password_hash,role,created_at) VALUES(?,?,?,?,?)',
                             (username, email, password_hash(password), 'student', now)).lastrowid
            db.execute('UPDATE users SET student_code=? WHERE id=?', (f'SV{uid:06d}', uid))
            return 201, {'message': 'Đăng ký thành công', 'role': 'student'}
        if method == 'POST' and path == '/auth/login':
            name = str(body.get('identifier', '')).strip()
            user = db.execute('SELECT * FROM users WHERE username=? OR email=?', (name, name.lower())).fetchone()
            require(user and password_ok(str(body.get('password', '')), user['password_hash']), 401, 'Sai tài khoản hoặc mật khẩu')
            code = f'{secrets.randbelow(1000000):06d}'
            db.execute('UPDATE otps SET used=1 WHERE user_id=?', (user['id'],))
            otp_id = db.execute('INSERT INTO otps(user_id,code_hash,expires_at) VALUES(?,?,?)',
                                (user['id'], hashlib.sha256(code.encode()).hexdigest(), now + OTP_MINUTES * 60)).lastrowid
            delivery = send_otp(user['email'], code)
            return 200, {'challengeId': otp_id, 'delivery': delivery, 'message': 'Nhập OTP để hoàn tất đăng nhập'}
        if method == 'POST' and path == '/auth/verify':
            otp = db.execute('SELECT * FROM otps WHERE id=?', (int(body.get('challengeId', 0)),)).fetchone()
            require(otp and not otp['used'] and otp['expires_at'] > now and otp['attempts'] < 5, 401, 'OTP hết hạn hoặc không hợp lệ')
            db.execute('UPDATE otps SET attempts=attempts+1 WHERE id=?', (otp['id'],))
            valid = hmac.compare_digest(otp['code_hash'], hashlib.sha256(str(body.get('code', '')).encode()).hexdigest())
            require(valid, 401, 'OTP không đúng')
            db.execute('UPDATE otps SET used=1 WHERE id=?', (otp['id'],))
            token = secrets.token_urlsafe(32)
            db.execute('INSERT INTO tokens VALUES(?,?,?)', (hashlib.sha256(token.encode()).hexdigest(), otp['user_id'], now + 7*86400))
            user = db.execute('SELECT id,username,email,role FROM users WHERE id=?', (otp['user_id'],)).fetchone()
            return 200, {'token': token, 'user': dict(user)}
        if method == 'POST' and path == '/auth/face/login':
            identifier = str(body.get('identifier', '')).strip().lower()
            require(3 <= len(identifier) <= 254, 400, 'Nhập username hoặc email trước khi quét')
            user = db.execute('SELECT id,username,email,role FROM users WHERE lower(username)=? OR email=?',
                              (identifier, identifier)).fetchone()
            rate_key = f"user:{user['id']}" if user else f'name:{identifier}'
            attempt = db.execute('SELECT * FROM face_attempts WHERE identifier=?', (rate_key,)).fetchone()
            if attempt and attempt['window_start'] > now - 600:
                require(attempt['attempts'] < 5, 429, 'Quét sai nhiều lần, hãy thử lại sau 10 phút')
                db.execute('UPDATE face_attempts SET attempts=attempts+1 WHERE identifier=?', (rate_key,))
            else:
                db.execute('INSERT OR REPLACE INTO face_attempts VALUES(?,?,?)', (rate_key, 1, now))
            db.commit()  # Count failed scans even when verification raises an error.
            verify_registered_face(db, user, body.get('images'),
                                   'Khuôn mặt không khớp hoặc chưa quay đầu đúng cách')
            db.execute('DELETE FROM face_attempts WHERE identifier=?', (rate_key,))
            token = secrets.token_urlsafe(32)
            db.execute('INSERT INTO tokens VALUES(?,?,?)',
                       (hashlib.sha256(token.encode()).hexdigest(), user['id'], now + 7*86400))
            return 200, {'token': token, 'user': dict(user)}
        user = self.actor(db)
        if method == 'POST' and path == '/face/analyze':
            return 200, face_auth.analyze(body.get('image'))
        if method == 'GET' and path == '/me': return 200, user
        if method == 'GET' and path == '/me/face':
            enrolled = db.execute('SELECT 1 FROM face_templates WHERE user_id=?', (user['id'],)).fetchone()
            return 200, {'enrolled': bool(enrolled)}
        if method == 'POST' and path == '/me/face/enroll':
            features = face_auth.enroll(body.get('images'))
            db.execute('INSERT OR REPLACE INTO face_templates VALUES(?,?,?)',
                       (user['id'], json.dumps(features), now))
            return 200, {'message': 'Đã đăng ký khuôn mặt'}
        if method == 'DELETE' and path == '/me/face':
            db.execute('DELETE FROM face_templates WHERE user_id=?', (user['id'],))
            return 200, {'message': 'Đã xóa mẫu khuôn mặt'}
        if method == 'GET' and path == '/me/insights':
            require(user['role'] == 'student', 403, 'Chỉ sinh viên')
            rows = db.execute('''SELECT sessions.id,classes.name,attendance.checked_at
                FROM sessions JOIN classes ON classes.id=sessions.class_id
                JOIN enrollments ON enrollments.class_id=classes.id AND enrollments.user_id=?
                LEFT JOIN attendance ON attendance.session_id=sessions.id AND attendance.user_id=?
                WHERE sessions.ends_at<? ORDER BY sessions.ends_at DESC''',
                (user['id'], user['id'], now)).fetchall()
            total = len(rows)
            present = sum(1 for x in rows if x['checked_at'] is not None)
            rate = round(present * 100 / total) if total else None
            return 200, {'completed': total, 'present': present, 'rate': rate,
                         'atRisk': total >= 3 and rate < 80,
                         'missed': [{'sessionId': x['id'], 'className': x['name']}
                                    for x in rows if x['checked_at'] is None][:5]}
        if method == 'POST' and path == '/auth/logout':
            db.execute('DELETE FROM tokens WHERE token_hash=?', (hashlib.sha256(self.headers['Authorization'][7:].encode()).hexdigest(),))
            return 200, {'message': 'Đã đăng xuất'}
        if path == '/users' and method == 'GET':
            require(user['role'] == 'admin', 403, 'Chỉ admin')
            return 200, {'items': [dict(x) for x in db.execute('SELECT id,username,email,role FROM users ORDER BY id')]}
        if path.startswith('/users/') and method == 'PUT':
            require(user['role'] == 'admin', 403, 'Chỉ admin')
            uid = int(path.split('/')[-1]); role = body.get('role')
            require(role in ('admin', 'teacher', 'student'), 400, 'Role không hợp lệ')
            require(uid != user['id'] or role == 'admin', 400, 'Không thể tự bỏ quyền admin')
            changed = db.execute('UPDATE users SET role=? WHERE id=?', (role, uid)).rowcount
            require(changed, 404, 'Không tìm thấy người dùng')
            return 200, {'message': 'Đã cập nhật'}
        if path == '/classes' and method == 'GET':
            if user['role'] == 'admin': rows = db.execute('SELECT * FROM classes ORDER BY id DESC')
            elif user['role'] == 'teacher': rows = db.execute('SELECT * FROM classes WHERE teacher_id=? ORDER BY id DESC', (user['id'],))
            else: rows = db.execute('SELECT classes.* FROM classes JOIN enrollments ON enrollments.class_id=classes.id WHERE enrollments.user_id=? ORDER BY classes.id DESC', (user['id'],))
            return 200, {'items': [dict(x) for x in rows]}
        if path == '/classes' and method == 'POST':
            require(user['role'] in ('admin', 'teacher'), 403, 'Chỉ giảng viên/admin')
            name = str(body.get('name', '')).strip(); require(1 <= len(name) <= 100, 400, 'Tên lớp không hợp lệ')
            teacher_id = int(body.get('teacherId', user['id'])) if user['role'] == 'admin' else user['id']
            require(db.execute('SELECT 1 FROM users WHERE id=? AND role="teacher"', (teacher_id,)).fetchone() or teacher_id == user['id'], 400, 'Giảng viên không hợp lệ')
            code = secrets.token_hex(4).upper()
            cid = db.execute('INSERT INTO classes(name,room,teacher_id,join_code,created_at) VALUES(?,?,?,?,?)',
                             (name, str(body.get('room', '')).strip()[:100], teacher_id, code, now)).lastrowid
            return 201, {'id': cid, 'joinCode': code}
        if path == '/classes/join' and method == 'POST':
            require(user['role'] == 'student', 403, 'Chỉ sinh viên')
            cls = db.execute('SELECT id FROM classes WHERE join_code=?', (str(body.get('code', '')).upper().strip(),)).fetchone()
            require(cls, 404, 'Mã lớp không đúng')
            db.execute('INSERT OR IGNORE INTO enrollments VALUES(?,?)', (cls['id'], user['id']))
            return 200, {'message': 'Đã tham gia lớp'}
        parts = path.strip('/').split('/')
        if len(parts) >= 2 and parts[0] == 'classes' and parts[1].isdigit():
            cid = int(parts[1]); cls = db.execute('SELECT * FROM classes WHERE id=?', (cid,)).fetchone()
            require(cls, 404, 'Không tìm thấy lớp')
            owns = user['role'] == 'admin' or cls['teacher_id'] == user['id']
            member = owns or db.execute('SELECT 1 FROM enrollments WHERE class_id=? AND user_id=?', (cid, user['id'])).fetchone()
            require(member, 403, 'Không thuộc lớp')
            if len(parts) == 2 and method == 'PUT':
                require(owns, 403, 'Không có quyền sửa lớp')
                name = str(body.get('name', cls['name'])).strip(); require(name, 400, 'Thiếu tên lớp')
                db.execute('UPDATE classes SET name=?,room=? WHERE id=?', (name[:100], str(body.get('room', cls['room']))[:100], cid))
                return 200, {'message': 'Đã cập nhật'}
            if len(parts) == 2 and method == 'DELETE':
                require(owns, 403, 'Không có quyền xóa lớp')
                db.execute('DELETE FROM classes WHERE id=?', (cid,))
                return 200, {'message': 'Đã xóa'}
            if len(parts) == 3 and parts[2] == 'students' and method == 'GET':
                require(owns, 403, 'Không có quyền xem')
                return 200, {'items': [dict(x) for x in db.execute('SELECT users.id,username,email FROM users JOIN enrollments ON users.id=enrollments.user_id WHERE class_id=?', (cid,))]}
            if len(parts) == 3 and parts[2] == 'sessions' and method == 'GET':
                rows = [dict(x) for x in db.execute('SELECT * FROM sessions WHERE class_id=? ORDER BY id DESC', (cid,))]
                if not owns:
                    for row in rows:
                        row.pop('code', None)
                return 200, {'items': rows}
            if len(parts) == 3 and parts[2] == 'sessions' and method == 'POST':
                require(owns, 403, 'Không có quyền mở điểm danh')
                minutes = int(body.get('minutes', 15)); require(1 <= minutes <= 180, 400, 'Thời lượng 1-180 phút')
                lat, lon, radius = body.get('latitude'), body.get('longitude'), body.get('radiusM')
                require(valid_coordinates(lat, lon), 400, 'Cần vị trí giảng viên để mở điểm danh')
                try:
                    radius = float(radius)
                except (TypeError, ValueError):
                    raise ApiError(400, 'Bán kính điểm danh không hợp lệ')
                require(isfinite(radius) and 1 <= radius <= 5000, 400, 'Bán kính điểm danh không hợp lệ')
                code = f'{secrets.randbelow(1000000):06d}'
                sid = db.execute('INSERT INTO sessions(class_id,starts_at,ends_at,code,latitude,longitude,radius_m,created_at) VALUES(?,?,?,?,?,?,?,?)',
                                 (cid, now, now + minutes*60, code, lat, lon, radius, now)).lastrowid
                return 201, {'id': sid, 'code': code, 'endsAt': now + minutes*60}
        if len(parts) >= 2 and parts[0] == 'sessions' and parts[1].isdigit():
            sid = int(parts[1]); session = db.execute('SELECT sessions.*,classes.teacher_id FROM sessions JOIN classes ON classes.id=sessions.class_id WHERE sessions.id=?', (sid,)).fetchone()
            require(session, 404, 'Không tìm thấy buổi điểm danh')
            owns = user['role'] == 'admin' or session['teacher_id'] == user['id']
            enrolled = db.execute('SELECT 1 FROM enrollments WHERE class_id=? AND user_id=?', (session['class_id'], user['id'])).fetchone()
            require(owns or enrolled, 403, 'Không thuộc lớp')
            if len(parts) == 4 and parts[2:] == ['attendance', 'status'] and method == 'GET':
                require(enrolled and user['role'] == 'student', 403, 'Chỉ sinh viên trong lớp')
                record = db.execute('SELECT checked_at,method FROM attendance WHERE session_id=? AND user_id=?',
                                    (sid, user['id'])).fetchone()
                return 200, {'hasAttended': bool(record), 'sessionId': sid,
                             'userId': user['id'], 'name': user['username'],
                             'studentCode': user['student_code'],
                             'checkedAt': record['checked_at'] if record else None,
                             'status': 'Có mặt' if record else None,
                             'method': record['method'] if record else None}
            if len(parts) == 4 and parts[2:] == ['code', 'validate'] and method == 'POST':
                require(enrolled and user['role'] == 'student', 403, 'Chỉ sinh viên trong lớp')
                require(session['starts_at'] <= now <= session['ends_at'], 409, 'Buổi điểm danh đã đóng')
                if db.execute('SELECT 1 FROM attendance WHERE session_id=? AND user_id=?',
                              (sid, user['id'])).fetchone():
                    raise ApiError(409, 'Bạn đã điểm danh buổi này rồi.', 'ALREADY_ATTENDED')
                require(hmac.compare_digest(str(body.get('code', '')), session['code']), 400, 'Mã điểm danh không đúng')
                return 200, {'valid': True}
            if len(parts) == 3 and parts[2] in ('face-verify', 'checkin') and method == 'POST':
                require(enrolled and user['role'] == 'student', 403, 'Chỉ sinh viên trong lớp')
                require(session['starts_at'] <= now <= session['ends_at'], 409, 'Buổi điểm danh đã đóng')
                if db.execute('SELECT 1 FROM attendance WHERE session_id=? AND user_id=?',
                              (sid, user['id'])).fetchone():
                    raise ApiError(409, 'Bạn đã điểm danh buổi này rồi.', 'ALREADY_ATTENDED')
                require(hmac.compare_digest(str(body.get('code', '')), session['code']), 400, 'Mã điểm danh không đúng')
                if parts[2] == 'face-verify':
                    verify_registered_face(db, user, body.get('images'),
                                           'Khuôn mặt không khớp với tài khoản đang đăng nhập.')
                    proof = secrets.token_urlsafe(32)
                    db.execute('DELETE FROM face_checkin_proofs WHERE expires_at<=?', (now,))
                    db.execute('INSERT INTO face_checkin_proofs VALUES(?,?,?,?,?)',
                               (hashlib.sha256(proof.encode()).hexdigest(), user['id'], sid,
                                hashlib.sha256(session['code'].encode()).hexdigest(), now + 180))
                    return 200, {'faceVerified': True, 'faceProof': proof, 'expiresAt': now + 180,
                                 'userId': user['id'], 'name': user['username'],
                                 'studentCode': user['student_code']}
                require(body.get('faceVerified') is True, 403, 'Cần quét khuôn mặt trước')
                require(body.get('userId') == user['id'], 403, 'Tài khoản điểm danh không hợp lệ')
                proof = str(body.get('faceProof', ''))
                require(len(proof) >= 32, 403, 'Cần quét khuôn mặt trước')
                proof_hash = hashlib.sha256(proof.encode()).hexdigest()
                verified = db.execute('''SELECT 1 FROM face_checkin_proofs
                    WHERE proof_hash=? AND user_id=? AND session_id=? AND code_hash=? AND expires_at>?''',
                    (proof_hash, user['id'], sid,
                     hashlib.sha256(session['code'].encode()).hexdigest(), now)).fetchone()
                require(verified, 403, 'Xác thực khuôn mặt đã hết hạn, hãy quét lại')
                lat, lon = body.get('latitude'), body.get('longitude')
                require(lat is not None and lon is not None, 400, 'Cần bật định vị và chia sẻ vị trí')
                require(valid_coordinates(lat, lon), 400, 'Tọa độ không hợp lệ')
                if session['radius_m'] is not None:
                    require(distance_m(session['latitude'], session['longitude'], lat, lon) <= session['radius_m'], 403, 'Ngoài phạm vi điểm danh')
                inserted = db.execute('INSERT OR IGNORE INTO attendance VALUES(?,?,?,?,?,?)',
                                      (sid, user['id'], now, lat, lon, 'face')).rowcount
                if not inserted:
                    raise ApiError(409, 'Bạn đã điểm danh buổi này rồi.', 'ALREADY_ATTENDED')
                db.execute('DELETE FROM face_checkin_proofs WHERE proof_hash=?', (proof_hash,))
                return 201, {'message': 'Điểm danh thành công', 'checkedAt': now,
                             'userId': user['id'], 'name': user['username'],
                             'studentCode': user['student_code'], 'status': 'Có mặt', 'method': 'face'}
            if len(parts) == 3 and parts[2] == 'attendance' and method == 'GET':
                require(owns, 403, 'Không có quyền xem')
                return 200, {'items': [dict(x) for x in db.execute('SELECT users.username,users.email,attendance.* FROM attendance JOIN users ON users.id=attendance.user_id WHERE session_id=? ORDER BY checked_at', (sid,))]}
        raise ApiError(404, 'Không tìm thấy API')


if __name__ == '__main__':
    init_db()
    print(f'API: http://{HOST}:{PORT}', flush=True)
    ThreadingHTTPServer((HOST, PORT), Handler).serve_forever()
