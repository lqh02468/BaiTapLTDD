"""Local OpenCV face matching. Images are processed in memory, never stored."""

import base64
import binascii
import threading
from pathlib import Path

MODEL_DIR = Path(__file__).with_name('models')
_lock = threading.Lock()
_detector = None
_recognizer = None


class FaceError(ValueError):
    pass


def _models():
    global _detector, _recognizer
    if _detector is None:
        try:
            import cv2
            detector = cv2.FaceDetectorYN.create(
                str(MODEL_DIR / 'yunet.onnx'), '', (640, 480), score_threshold=0.85)
            recognizer = cv2.FaceRecognizerSF.create(
                str(MODEL_DIR / 'sface_int8.onnx'), '')
            _detector, _recognizer = detector, recognizer
        except Exception as exc:
            raise FaceError('Backend chưa cài OpenCV hoặc thiếu mô hình khuôn mặt') from exc
    return _detector, _recognizer


def check_ready():
    _models()


def analyze(image_b64):
    try:
        try:
            import cv2
            import numpy as np
        except ImportError as exc:
            raise FaceError('Backend chưa cài OpenCV hoặc NumPy để nhận diện khuôn mặt') from exc
        raw = base64.b64decode(image_b64, validate=True)
        if not 5000 <= len(raw) <= 350000:
            raise FaceError('Ảnh khuôn mặt không hợp lệ')
        image = cv2.imdecode(np.frombuffer(raw, np.uint8), cv2.IMREAD_COLOR)
        if image is None or not (240 <= image.shape[0] <= 1280 and 240 <= image.shape[1] <= 1280):
            raise FaceError('Kích thước ảnh không hợp lệ')
        if cv2.Laplacian(image, cv2.CV_64F).var() < 20:
            raise FaceError('Ảnh bị mờ, hãy giữ điện thoại ổn định')
        with _lock:
            detector, recognizer = _models()
            detector.setInputSize((image.shape[1], image.shape[0]))
            _, faces = detector.detect(image)
            if faces is None or len(faces) != 1:
                raise FaceError('Cần đúng một khuôn mặt rõ trong khung')
            face = faces[0]
            if face[2] < 95 or face[3] < 95:
                raise FaceError('Hãy đưa khuôn mặt gần camera hơn')
            aligned = recognizer.alignCrop(image, face)
            feature = recognizer.feature(aligned).flatten().astype('float32')
        norm = float(np.linalg.norm(feature))
        if norm < 1e-6:
            raise FaceError('Không đọc được đặc trưng khuôn mặt')
        feature = feature / norm
        eye_mid = (float(face[4]) + float(face[6])) / 2
        eye_distance = abs(float(face[4]) - float(face[6]))
        yaw = (float(face[8]) - eye_mid) / max(eye_distance, 1)
        return {
            'embedding': feature.tolist(),
            'yaw': yaw,
            'bounds': [float(value) for value in face[:4]],
            'landmarks': {
                'rightEye': [float(face[4]), float(face[5])],
                'leftEye': [float(face[6]), float(face[7])],
                'nose': [float(face[8]), float(face[9])],
                'rightMouth': [float(face[10]), float(face[11])],
                'leftMouth': [float(face[12]), float(face[13])],
            },
        }
    except (binascii.Error, TypeError):
        raise FaceError('Ảnh khuôn mặt không hợp lệ')


def describe(image_b64):
    result = analyze(image_b64)
    return result['embedding'], result['yaw']


def similarity(a, b):
    return sum(float(x) * float(y) for x, y in zip(a, b))


def enroll(images):
    if not isinstance(images, list) or len(images) != 3:
        raise FaceError('Cần 3 ảnh khuôn mặt để đăng ký')
    samples = [describe(image) for image in images]
    if any(abs(yaw) > 0.32 for _, yaw in samples):
        raise FaceError('Hãy nhìn thẳng camera khi đăng ký')
    features = [feature for feature, _ in samples]
    if min(similarity(features[i], features[j]) for i in range(3) for j in range(i + 1, 3)) < 0.35:
        raise FaceError('Các ảnh đăng ký không giống nhau, hãy thử lại')
    return features


def verify(images, templates):
    if not isinstance(images, list) or len(images) != 2:
        raise FaceError('Cần hai ảnh để xác thực')
    straight, first_yaw = describe(images[0])
    turned, second_yaw = describe(images[1])
    if abs(first_yaw) > 0.28 or abs(second_yaw - first_yaw) < 0.16:
        raise FaceError('Hãy nhìn thẳng rồi quay đầu sang một bên theo hướng dẫn')
    if max(similarity(straight, template) for template in templates) < 0.42:
        raise FaceError('Khuôn mặt không khớp tài khoản')
    if max(similarity(turned, template) for template in templates) < 0.30:
        raise FaceError('Khuôn mặt thứ hai không khớp tài khoản')
    return True
