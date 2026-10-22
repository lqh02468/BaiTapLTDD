import contextlib
import io
import json
import os
import re
import tempfile
import threading
import unittest
from unittest.mock import patch
from http.server import ThreadingHTTPServer
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import server
from email_service import EmailConfigurationError, EmailService


class ApiTest(unittest.TestCase):
    def test_face_runtime_health_reports_missing_models(self):
        with patch.object(server.face_auth, 'check_ready', side_effect=server.face_auth.FaceError('OpenCV missing')):
            status, body = self.call('GET', '/health/face')
        self.assertEqual(status, 503)
        self.assertEqual(body['message'], 'OpenCV missing')
        with patch.object(server.face_auth, 'check_ready'):
            status, body = self.call('GET', '/health/face')
        self.assertEqual((status, body), (200, {'status': 'ok'}))

    def test_email_service_configuration_and_smtp(self):
        with patch.dict(os.environ, {'APP_ENV': 'Production', 'SMTP_HOST': '',
                                     'SMTP_USER': '', 'SMTP_PASSWORD': '', 'SMTP_FROM': ''}):
            with self.assertRaises(EmailConfigurationError):
                EmailService().send_otp('recipient@example.test', '482913', 5)
        config = {'APP_ENV': 'Production', 'SMTP_HOST': 'smtp.example.test',
                  'SMTP_PORT': '587', 'SMTP_USER': 'sender@example.test',
                  'SMTP_PASSWORD': 'app-password', 'SMTP_FROM': 'sender@example.test'}
        with patch.dict(os.environ, config), patch('email_service.smtplib.SMTP') as smtp:
            self.assertEqual(EmailService().send_otp('recipient@example.test', '482913', 5), 'email')
            smtp.return_value.__enter__.return_value.starttls.assert_called_once()
            smtp.return_value.__enter__.return_value.login.assert_called_once_with(
                'sender@example.test', 'app-password')
            message = smtp.return_value.__enter__.return_value.send_message.call_args.args[0]
            self.assertEqual(message['To'], 'recipient@example.test')
            self.assertIn('482913', message.get_content())

    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        server.DB_PATH = __import__('pathlib').Path(cls.temp.name) / 'test.db'
        os.environ['BOOTSTRAP_ADMIN_EMAIL'] = 'admin@example.test'
        os.environ['BOOTSTRAP_ADMIN_PASSWORD'] = 'AdminPassword123!'
        os.environ['APP_ENV'] = 'Development'
        server.init_db()
        cls.http = ThreadingHTTPServer(('127.0.0.1', 0), server.Handler)
        cls.thread = threading.Thread(target=cls.http.serve_forever, daemon=True)
        cls.thread.start()
        cls.url = f'http://127.0.0.1:{cls.http.server_port}'

    @classmethod
    def tearDownClass(cls):
        cls.http.shutdown()
        cls.http.server_close()
        cls.temp.cleanup()
        os.environ.pop('BOOTSTRAP_ADMIN_EMAIL', None)
        os.environ.pop('BOOTSTRAP_ADMIN_PASSWORD', None)
        os.environ.pop('APP_ENV', None)

    def call(self, method, path, body=None, token=None):
        headers = {'Content-Type': 'application/json'}
        if token:
            headers['Authorization'] = f'Bearer {token}'
        req = Request(self.url + path, data=json.dumps(body).encode() if body is not None else None,
                      headers=headers, method=method)
        try:
            with urlopen(req) as res:
                return res.status, json.load(res)
        except HTTPError as error:
            with error:
                return error.code, json.load(error)

    def login(self, identifier, password):
        with server.connect() as db:
            db.execute('UPDATE otps SET created_at=0 WHERE user_id IN (SELECT id FROM users WHERE username=? OR email=?)',
                       (identifier, identifier))
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            status, challenge = self.call('POST', '/auth/login', {'identifier': identifier, 'password': password})
        self.assertEqual(status, 200)
        if 'token' in challenge:
            self.assertNotIn('challengeId', challenge)
            return challenge['token']
        code = re.search(r': (\d{6})', output.getvalue()).group(1)
        status, result = self.call('POST', '/auth/verify', {'challengeId': challenge['challengeId'], 'code': code})
        self.assertEqual(status, 200)
        self.assertEqual(self.call('POST', '/auth/verify', {'challengeId': challenge['challengeId'], 'code': code})[0], 401)
        return result['token']

    def test_admin_password_login_without_otp(self):
        with server.connect() as db:
            admin_id = db.execute("SELECT id FROM users WHERE username='admin' AND role='admin'").fetchone()[0]
            before = db.execute('SELECT COUNT(*) FROM otps WHERE user_id=?', (admin_id,)).fetchone()[0]
        with patch.dict(os.environ, {'APP_ENV': 'Production', 'SMTP_HOST': '',
                                     'SMTP_USER': '', 'SMTP_PASSWORD': '', 'SMTP_FROM': ''}):
            self.assertEqual(self.call('POST', '/auth/login',
                                       {'identifier': 'admin', 'password': 'incorrect'})[0], 401)
            status, result = self.call('POST', '/auth/login',
                                       {'identifier': 'admin', 'password': 'AdminPassword123!'})
        self.assertEqual(status, 200)
        self.assertNotIn('challengeId', result)
        self.assertEqual(result['user']['role'], 'admin')
        self.assertEqual(self.call('GET', '/me', token=result['token'])[1]['username'], 'admin')
        with server.connect() as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM otps WHERE user_id=?',
                                        (admin_id,)).fetchone()[0], before)

    def register(self, body):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            status, challenge = self.call('POST', '/auth/register', body)
        if status != 201:
            return status, challenge
        code = re.search(r': (\d{6})', output.getvalue()).group(1)
        verified = self.call('POST', '/auth/register/verify',
                             {'challengeId': challenge['challengeId'], 'code': code})
        self.assertEqual(verified[0], 200)
        return status, challenge

    def test_registration_otp_guards(self):
        body = {'username': 'otp_guard', 'email': 'otp_guard@example.test', 'password': 'Password123'}
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            status, first = self.call('POST', '/auth/register', body)
        self.assertEqual(status, 201)
        self.assertNotIn('otp', first)
        code = re.search(r': (\d{6})', output.getvalue()).group(1)
        self.assertEqual(self.call('POST', '/auth/login',
                                   {'identifier': body['username'], 'password': body['password']})[0], 401)
        self.assertEqual(self.call('POST', '/auth/register', body)[0], 429)
        wrong = '000000' if code != '000000' else '111111'
        self.assertEqual(self.call('POST', '/auth/register/verify',
                                   {'challengeId': first['challengeId'], 'code': wrong})[0], 401)
        with server.connect() as db:
            self.assertEqual(db.execute('SELECT attempts FROM pending_registrations WHERE id=?',
                                        (first['challengeId'],)).fetchone()[0], 1)
            db.execute('UPDATE pending_registrations SET created_at=0 WHERE id=?',
                       (first['challengeId'],))
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            status, second = self.call('POST', '/auth/register', body)
        self.assertEqual(status, 201)
        new_code = re.search(r': (\d{6})', output.getvalue()).group(1)
        self.assertEqual(self.call('POST', '/auth/register/verify',
                                   {'challengeId': first['challengeId'], 'code': code})[0], 401)
        with server.connect() as db:
            db.execute('UPDATE pending_registrations SET expires_at=0 WHERE id=?',
                       (second['challengeId'],))
        self.assertEqual(self.call('POST', '/auth/register/verify',
                                   {'challengeId': second['challengeId'], 'code': new_code})[0], 401)
        with server.connect() as db:
            db.execute('UPDATE pending_registrations SET expires_at=? WHERE id=?',
                       (int(__import__('time').time()) + 300, second['challengeId']))
        self.assertEqual(self.call('POST', '/auth/register/verify',
                                   {'challengeId': second['challengeId'], 'code': new_code})[0], 200)
        self.assertEqual(self.call('POST', '/auth/register/verify',
                                   {'challengeId': second['challengeId'], 'code': new_code})[0], 401)

    def test_login_otp_guards(self):
        self.register({'username': 'login_guard', 'email': 'login_guard@example.test',
                       'password': 'Password123'})
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            status, first = self.call('POST', '/auth/login',
                                      {'identifier': 'login_guard', 'password': 'Password123'})
        self.assertEqual(status, 200)
        code = re.search(r': (\d{6})', output.getvalue()).group(1)
        self.assertEqual(self.call('POST', '/auth/login',
                                   {'identifier': 'login_guard', 'password': 'Password123'})[0], 429)
        wrong = '000000' if code != '000000' else '111111'
        for _ in range(5):
            self.assertEqual(self.call('POST', '/auth/verify',
                                       {'challengeId': first['challengeId'], 'code': wrong})[0], 401)
        self.assertEqual(self.call('POST', '/auth/verify',
                                   {'challengeId': first['challengeId'], 'code': code})[0], 401)
        with server.connect() as db:
            db.execute('UPDATE otps SET created_at=0 WHERE id=?', (first['challengeId'],))
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            status, second = self.call('POST', '/auth/login',
                                       {'identifier': 'login_guard', 'password': 'Password123'})
        self.assertEqual(status, 200)
        new_code = re.search(r': (\d{6})', output.getvalue()).group(1)
        with server.connect() as db:
            db.execute('UPDATE otps SET expires_at=0 WHERE id=?', (second['challengeId'],))
        self.assertEqual(self.call('POST', '/auth/verify',
                                   {'challengeId': second['challengeId'], 'code': new_code})[0], 401)
        with server.connect() as db:
            db.execute('UPDATE otps SET expires_at=? WHERE id=?',
                       (int(__import__('time').time()) + 300, second['challengeId']))
        self.assertEqual(self.call('POST', '/auth/verify',
                                   {'challengeId': second['challengeId'], 'code': new_code})[0], 200)
        self.assertEqual(self.call('POST', '/auth/verify',
                                   {'challengeId': second['challengeId'], 'code': new_code})[0], 401)

    def test_production_rejects_missing_smtp_without_creating_challenge(self):
        body = {'username': 'no_smtp_user', 'email': 'no_smtp@example.test',
                'password': 'Password123'}
        with patch.dict(os.environ, {'APP_ENV': 'Production', 'SMTP_HOST': '',
                                     'SMTP_USER': '', 'SMTP_PASSWORD': '', 'SMTP_FROM': ''}):
            status, result = self.call('POST', '/auth/register', body)
        self.assertEqual(status, 503)
        self.assertNotIn('challengeId', result)
        with server.connect() as db:
            self.assertIsNone(db.execute('SELECT 1 FROM pending_registrations WHERE email=?',
                                         (body['email'],)).fetchone())

    def face_proof(self, session_id, code, token):
        with patch.object(server.face_auth, 'verify', return_value=True):
            status, result = self.call('POST', f'/sessions/{session_id}/face-verify',
                                       {'code': code, 'images': ['front', 'turn']}, token)
        self.assertEqual(status, 200)
        self.assertTrue(result['faceVerified'])
        return result['faceProof']

    def test_face_enrollment_and_login_controls(self):
        self.assertEqual(self.register({
            'username': 'face_student', 'email': 'face@example.test', 'password': 'Password123'})[0], 201)
        token = self.login('face_student', 'Password123')
        self.assertEqual(self.call('GET', '/me/face', token=token)[1]['enrolled'], False)
        self.assertEqual(self.call('POST', '/me/face/enroll', {'images': ['a']})[0], 401)
        with patch.object(server.face_auth, 'enroll', side_effect=server.face_auth.FaceError('Invalid face')):
            self.assertEqual(self.call('POST', '/me/face/enroll',
                                       {'images': ['a', 'b', 'c']}, token)[0], 400)
        with patch.object(server.face_auth, 'enroll', return_value=[[1.0, 0.0]] * 3):
            status, _ = self.call('POST', '/me/face/enroll', {'images': ['a', 'b', 'c']}, token)
        self.assertEqual(status, 200)
        self.assertEqual(self.call('GET', '/me/face', token=token)[1]['enrolled'], True)
        self.assertEqual(self.register({
            'username': 'face_student_b', 'email': 'face_b@example.test', 'password': 'Password123'})[0], 201)
        token_b = self.login('face_student_b', 'Password123')
        with patch.object(server.face_auth, 'enroll', return_value=[[1.0, 0.0]] * 3):
            self.assertEqual(self.call('POST', '/me/face/enroll',
                                       {'images': ['a', 'b', 'c']}, token_b)[0], 200)
        with server.connect() as db:
            templates = db.execute('''SELECT face_templates.user_id,features FROM face_templates
                JOIN users ON users.id=face_templates.user_id
                WHERE users.username IN ('face_student','face_student_b')
                ORDER BY face_templates.user_id''').fetchall()
        self.assertEqual(len(templates), 2)
        self.assertEqual(templates[0]['features'], templates[1]['features'])
        self.assertNotEqual(templates[0]['user_id'], templates[1]['user_id'])
        with patch.object(server.face_auth, 'verify', return_value=True) as verify:
            status, result = self.call('POST', '/auth/face/login', {
                'identifier': 'face_student', 'images': ['front', 'turn']})
            status_b, result_b = self.call('POST', '/auth/face/login', {
                'identifier': 'face_student_b', 'images': ['front', 'turn']})
        self.assertEqual(status, 200)
        self.assertEqual(status_b, 200)
        self.assertEqual(result['user']['username'], 'face_student')
        self.assertEqual(result_b['user']['username'], 'face_student_b')
        self.assertEqual(self.call('GET', '/me', token=result['token'])[0], 200)
        self.assertEqual(verify.call_count, 2)
        self.assertEqual(self.call('DELETE', '/me/face', token=token)[0], 200)
        self.assertEqual(self.call('GET', '/me/face', token=token_b)[1]['enrolled'], True)
        self.assertEqual(self.call('POST', '/auth/face/login', {
            'identifier': 'face_student', 'images': ['front', 'turn']})[0], 401)
        for identifier in ('face@example.test', 'face_student', 'face@example.test', 'face_student'):
            self.assertEqual(self.call('POST', '/auth/face/login', {
                'identifier': identifier, 'images': ['front', 'turn']})[0], 401)
        self.assertEqual(self.call('POST', '/auth/face/login', {
            'identifier': 'face_student', 'images': ['front', 'turn']})[0], 429)

    def test_face_checkin_reuses_login_template_and_account(self):
        self.assertEqual(self.register({
            'username': 'face_teacher', 'email': 'face_teacher@example.test',
            'password': 'Password123'})[0], 201)
        admin = self.login('admin@example.test', 'AdminPassword123!')
        users = self.call('GET', '/users', token=admin)[1]['items']
        teacher_id = next(u['id'] for u in users if u['username'] == 'face_teacher')
        self.assertEqual(self.call('PUT', f'/users/{teacher_id}',
                                   {'role': 'teacher'}, admin)[0], 200)
        teacher = self.login('face_teacher', 'Password123')
        cls = self.call('POST', '/classes', {'name': 'Face checkin'}, teacher)[1]
        tokens = []
        for suffix in ('a', 'b'):
            name = f'face_checkin_{suffix}'
            self.assertEqual(self.register({
                'username': name, 'email': f'{name}@example.test',
                'password': 'Password123'})[0], 201)
            token = self.login(name, 'Password123')
            tokens.append(token)
            self.assertEqual(self.call('POST', '/classes/join',
                                       {'code': cls['joinCode']}, token)[0], 200)
            with patch.object(server.face_auth, 'enroll', return_value=[[1.0, 0.0]] * 3):
                self.assertEqual(self.call('POST', '/me/face/enroll',
                                           {'images': ['front', 'front', 'front']}, token)[0], 200)
        session = self.call('POST', f"/classes/{cls['id']}/sessions",
                            {'minutes': 15, 'latitude': 10.0,
                             'longitude': 106.0, 'radiusM': 100}, teacher)[1]
        path = f"/sessions/{session['id']}/face-verify"
        checkin_path = f"/sessions/{session['id']}/checkin"
        status_path = f"/sessions/{session['id']}/attendance/status"
        body = {'code': session['code'], 'images': ['front', 'turn']}
        self.assertFalse(self.call('GET', status_path, token=tokens[0])[1]['hasAttended'])
        self.assertEqual(self.call('POST', checkin_path, {'code': session['code']}, tokens[0])[0], 403)
        with patch.object(server.face_auth, 'verify', side_effect=server.face_auth.FaceError('not match')):
            status, response = self.call('POST', path, body, tokens[1])
        self.assertEqual(status, 401)
        self.assertEqual(response['error'], 'Khuôn mặt không khớp với tài khoản đang đăng nhập.')
        wrong_code = '000000' if session['code'] != '000000' else '111111'
        self.assertEqual(self.call('POST', path, {**body, 'code': wrong_code}, tokens[0])[0], 400)
        with server.connect() as db:
            token_count_before = db.execute('SELECT COUNT(*) FROM tokens').fetchone()[0]
        with patch.object(server.face_auth, 'verify', return_value=True) as verify:
            first = self.call('POST', path, body, tokens[0])
            second = self.call('POST', path, body, tokens[1])
        with server.connect() as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM tokens').fetchone()[0],
                             token_count_before)
        self.assertEqual(first[0], 200)
        self.assertEqual(second[0], 200)
        self.assertFalse(self.call('GET', status_path, token=tokens[0])[1]['hasAttended'])
        self.assertEqual(self.call('POST', checkin_path,
            {'code': session['code'], 'userId': first[1]['userId'], 'faceVerified': True,
             'faceProof': first[1]['faceProof']}, tokens[0])[0], 400)
        self.assertEqual(self.call('POST', checkin_path,
            {'code': session['code'], 'userId': first[1]['userId'], 'faceVerified': True,
             'faceProof': first[1]['faceProof'], 'latitude': 10, 'longitude': 106}, tokens[1])[0], 403)
        first_checkin = self.call('POST', checkin_path,
            {'code': session['code'], 'userId': first[1]['userId'], 'faceVerified': True,
             'faceProof': first[1]['faceProof'], 'latitude': 10, 'longitude': 106}, tokens[0])
        second_checkin = self.call('POST', checkin_path,
            {'code': session['code'], 'userId': second[1]['userId'], 'faceVerified': True,
             'faceProof': second[1]['faceProof'], 'latitude': 10, 'longitude': 106}, tokens[1])
        self.assertEqual(first_checkin[0], 201)
        self.assertEqual(second_checkin[0], 201)
        self.assertEqual(first_checkin[1]['method'], 'face')
        self.assertEqual(first_checkin[1]['name'], 'face_checkin_a')
        self.assertEqual(second_checkin[1]['name'], 'face_checkin_b')
        self.assertNotEqual(first_checkin[1]['userId'], second_checkin[1]['userId'])
        self.assertTrue(self.call('GET', status_path, token=tokens[0])[1]['hasAttended'])
        self.assertEqual(verify.call_count, 2)
        self.assertTrue(all(call.args[1] == [[1.0, 0.0]] * 3
                            for call in verify.call_args_list))
        attendance = self.call('GET', f"/sessions/{session['id']}/attendance", token=teacher)[1]['items']
        self.assertEqual({item['user_id'] for item in attendance},
                         {first_checkin[1]['userId'], second_checkin[1]['userId']})
        self.assertTrue(all(item['method'] == 'face' for item in attendance))
        duplicate = self.call('POST', checkin_path,
            {'code': session['code'], 'userId': first[1]['userId'], 'faceVerified': True,
             'faceProof': first[1]['faceProof'], 'latitude': 10, 'longitude': 106}, tokens[0])
        self.assertEqual(duplicate[0], 409)
        self.assertEqual(duplicate[1]['code'], 'ALREADY_ATTENDED')

    def test_attendance_and_permissions(self):
        self.assertEqual(self.call('GET', '/health')[0], 200)
        self.assertEqual(self.register({'username': 'teacher1', 'email': 'teacher@example.test', 'password': 'Password123'})[0], 201)
        self.assertEqual(self.register({'username': 'student1', 'email': 'student@example.test', 'password': 'Password123'})[0], 201)
        admin = self.login('admin@example.test', 'AdminPassword123!')
        student = self.login('student1', 'Password123')
        with patch.object(server.face_auth, 'enroll', return_value=[[1.0, 0.0]] * 3):
            self.assertEqual(self.call('POST', '/me/face/enroll',
                                       {'images': ['a', 'b', 'c']}, student)[0], 200)
        self.assertEqual(self.call('POST', '/classes', {'name': 'Math'}, student)[0], 403)
        users = self.call('GET', '/users', token=admin)[1]['items']
        teacher_id = next(u['id'] for u in users if u['username'] == 'teacher1')
        self.assertEqual(self.call('PUT', f'/users/{teacher_id}', {'role': 'teacher'}, admin)[0], 200)
        teacher = self.login('teacher1', 'Password123')
        status, cls = self.call('POST', '/classes', {'name': 'Math'}, teacher)
        self.assertEqual(status, 201)
        cid = cls['id']
        self.assertEqual(self.call('POST', '/classes/join', {'code': cls['joinCode']}, student)[0], 200)
        self.assertEqual(self.call('POST', f'/classes/{cid}/sessions',
                                   {'minutes': 15}, teacher)[0], 400)
        self.assertEqual(self.call('POST', f'/classes/{cid}/sessions',
            {'minutes': 15, 'latitude': 'unknown', 'longitude': 106.0,
             'radiusM': 100}, teacher)[0], 400)
        status, session = self.call('POST', f'/classes/{cid}/sessions',
            {'minutes': 15, 'latitude': 10.0, 'longitude': 106.0, 'radiusM': 100}, teacher)
        self.assertEqual(status, 201)
        sid = session['id']
        with server.connect() as db:
            saved = db.execute('SELECT latitude,longitude,radius_m FROM sessions WHERE id=?',
                               (sid,)).fetchone()
        self.assertEqual((saved['latitude'], saved['longitude'], saved['radius_m']),
                         (10.0, 106.0, 100.0))
        student_session = self.call('GET', f'/classes/{cid}/sessions', token=student)[1]['items'][0]
        self.assertNotIn('code', student_session)
        wrong_code = '000000' if session['code'] != '000000' else '111111'
        self.assertEqual(self.call('POST', f'/sessions/{sid}/code/validate', {'code': wrong_code}, student)[0], 400)
        self.assertEqual(self.call('POST', f'/sessions/{sid}/code/validate', {'code': session['code']}, student)[1]['valid'], True)
        self.assertEqual(self.call('POST', f'/sessions/{sid}/checkin', {'code': wrong_code}, student)[0], 400)
        self.assertEqual(self.call('POST', f'/sessions/{sid}/checkin', {'code': session['code']}, student)[0], 403)
        proof = self.face_proof(sid, session['code'], student)
        self.assertFalse(self.call('GET', f'/sessions/{sid}/attendance/status', token=student)[1]['hasAttended'])
        student_id = self.call('GET', '/me', token=student)[1]['id']
        checkin = {'code': session['code'], 'userId': student_id, 'faceVerified': True,
                   'faceProof': proof, 'latitude': 10.0, 'longitude': 106.0}
        self.assertEqual(self.call('POST', f'/sessions/{sid}/checkin',
                                    {**checkin, 'faceProof': 'x' * 43}, student)[0], 403)
        with server.connect() as db:
            db.execute('UPDATE face_checkin_proofs SET expires_at=0 WHERE session_id=?', (sid,))
        self.assertEqual(self.call('POST', f'/sessions/{sid}/checkin', checkin, student)[0], 403)
        checkin['faceProof'] = self.face_proof(sid, session['code'], student)
        self.assertEqual(self.call('POST', f'/sessions/{sid}/checkin', checkin, student)[0], 201)
        self.assertEqual(self.call('POST', f'/sessions/{sid}/checkin', checkin, student)[1]['code'], 'ALREADY_ATTENDED')
        student_again = self.login('student1', 'Password123')
        persisted = self.call('GET', f'/sessions/{sid}/attendance/status', token=student_again)[1]
        self.assertTrue(persisted['hasAttended'])
        self.assertEqual(persisted['status'], 'Có mặt')
        self.assertEqual(len(self.call('GET', f'/sessions/{sid}/attendance', token=teacher)[1]['items']), 1)
        self.assertEqual(self.call('GET', f'/sessions/{sid}/attendance', token=student)[0], 403)
        status, located = self.call('POST', f'/classes/{cid}/sessions',
            {'minutes': 15, 'latitude': 10.0, 'longitude': 106.0, 'radiusM': 100}, teacher)
        self.assertEqual(status, 201)
        lid = located['id']
        with patch.object(server.face_auth, 'verify', side_effect=server.face_auth.FaceError('not match')):
            self.assertEqual(self.call('POST', f'/sessions/{lid}/face-verify',
                {'code': located['code'], 'images': ['front', 'turn']}, student)[0], 401)
        located_proof = self.face_proof(lid, located['code'], student)
        located_body = {'code': located['code'], 'userId': student_id,
                        'faceVerified': True, 'faceProof': located_proof}
        self.assertEqual(self.call('POST', f'/sessions/{lid}/checkin',
            {**located_body, 'latitude': 11.0, 'longitude': 106.0}, student)[0], 403)
        self.assertEqual(self.call('POST', f'/sessions/{lid}/checkin',
            {**located_body, 'latitude': 'unknown', 'longitude': 106.0}, student)[0], 400)
        self.assertEqual(self.call('POST', f'/sessions/{lid}/checkin',
            {**located_body, 'latitude': 10.0, 'longitude': 106.0}, student)[0], 201)
        with server.connect() as db:
            saved_attendance = db.execute(
                'SELECT latitude,longitude FROM attendance WHERE session_id=? AND user_id=?',
                (lid, student_id)).fetchone()
        self.assertEqual((saved_attendance['latitude'], saved_attendance['longitude']),
                         (10.0, 106.0))
        self.assertEqual(self.call('POST', f'/classes/{cid}/sessions',
            {'minutes': 15, 'latitude': 10.0, 'longitude': 106.0,
             'radiusM': 100}, teacher)[0], 201)
        with server.connect() as db:
            db.execute('UPDATE sessions SET ends_at=0 WHERE class_id=?', (cid,))
        insight = self.call('GET', '/me/insights', token=student)[1]
        self.assertEqual(insight['completed'], 3)
        self.assertEqual(insight['present'], 2)
        self.assertTrue(insight['atRisk'])
        self.assertEqual(self.call('PUT', f'/classes/{cid}', {'name': 'Math 2'}, teacher)[0], 200)
        self.assertEqual(self.call('DELETE', f'/classes/{cid}', token=teacher)[0], 200)


if __name__ == '__main__':
    unittest.main()
