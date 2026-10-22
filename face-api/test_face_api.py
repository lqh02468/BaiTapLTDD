"""Smoke test FaceProfile storage, authorization and cosine recognition in isolation."""
import hashlib
import json
import os
from contextlib import closing
from pathlib import Path
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request


def request(url, method='GET', token=None, payload=None):
    data = None if payload is None else json.dumps(payload).encode()
    headers = {'Content-Type': 'application/json'}
    if token:
        headers['Authorization'] = f'Bearer {token}'
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=3) as response:
            return response.status, json.load(response)
    except urllib.error.HTTPError as error:
        return error.code, None


def main():
    project = Path(__file__).resolve().parent
    assembly = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else project / 'bin/Debug/net10.0/FaceApi.dll'
    with tempfile.TemporaryDirectory() as temp:
        db_path = Path(temp) / 'test.db'
        with closing(sqlite3.connect(db_path)) as db:
            db.executescript('''
                CREATE TABLE users(id INTEGER PRIMARY KEY, username TEXT, role TEXT, student_code TEXT);
                CREATE TABLE tokens(token_hash TEXT PRIMARY KEY, user_id INTEGER, expires_at INTEGER);
            ''')
            db.execute('INSERT INTO users VALUES(1,?,?,?)', ('Test Student', 'student', 'SV000001'))
            db.execute('INSERT INTO users VALUES(2,?,?,?)', ('Other Student', 'student', 'SV000002'))
            token = 'local-smoke-test-token-1234567890'
            token_b = 'local-smoke-test-token-abcdefghij'
            db.execute('INSERT INTO tokens VALUES(?,?,?)',
                       (hashlib.sha256(token.encode()).hexdigest(), 1, int(time.time()) + 600))
            db.execute('INSERT INTO tokens VALUES(?,?,?)',
                       (hashlib.sha256(token_b.encode()).hexdigest(), 2, int(time.time()) + 600))
            db.commit()
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0))
            port = sock.getsockname()[1]
        base = f'http://127.0.0.1:{port}'
        env = {**os.environ, 'ATTENDANCE_DB': str(db_path),
               'ASPNETCORE_URLS': base, 'DOTNET_CLI_TELEMETRY_OPTOUT': '1'}
        process = subprocess.Popen(['dotnet', str(assembly)],
                                   cwd=project, env=env, stdout=subprocess.DEVNULL,
                                   stderr=subprocess.PIPE)
        try:
            for _ in range(50):
                try:
                    if request(base + '/health')[0] == 200:
                        break
                except (OSError, urllib.error.URLError):
                    time.sleep(0.1)
            else:
                raise AssertionError('Face API did not start')
            assert request(base + '/api/face/profile')[0] == 401
            assert request(base + '/api/face/profile', token=token)[1]['enrolled'] is False
            embedding = [1.0] + [0.0] * 127
            assert request(base + '/api/face/profile', 'POST', token,
                           {'faceEmbedding': [0.0] * 128})[0] == 400
            assert request(base + '/api/face/profile', 'POST', token,
                           {'faceEmbedding': embedding})[0] == 200
            assert request(base + '/api/face/profile', 'POST', token_b,
                           {'faceEmbedding': embedding})[0] == 200
            assert request(base + '/api/face/profile', token=token)[1]['enrolled'] is True
            assert request(base + '/api/face/profile', token=token_b)[1]['enrolled'] is True
            match = request(base + '/api/face/recognize', 'POST', token,
                            {'faceEmbedding': embedding})[1]
            assert match['recognized'] and match['studentCode'] == 'SV000001'
            assert match['similarity'] == 100.0
            match_b = request(base + '/api/face/recognize', 'POST', token_b,
                              {'faceEmbedding': embedding})[1]
            assert match_b['recognized'] and match_b['studentCode'] == 'SV000002'
            miss = request(base + '/api/face/recognize', 'POST', token,
                           {'faceEmbedding': [0.0, 1.0] + [0.0] * 126})[1]
            assert miss['recognized'] is False
            assert request(base + '/api/face/profile', 'DELETE', token)[0] == 200
            assert request(base + '/api/face/profile', token=token)[1]['enrolled'] is False
            assert request(base + '/api/face/profile', token=token_b)[1]['enrolled'] is True
            print('Face API smoke test passed')
        finally:
            process.terminate()
            process.wait(timeout=5)


if __name__ == '__main__':
    main()
