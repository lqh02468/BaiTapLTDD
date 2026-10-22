"""SMTP delivery for one-time verification codes."""

import os
import smtplib
import ssl
from email.message import EmailMessage


class EmailConfigurationError(Exception):
    pass


class EmailService:
    def send_otp(self, address: str, code: str, minutes: int) -> str:
        host = os.getenv('SMTP_HOST', '').strip()
        username = os.getenv('SMTP_USER', '').strip()
        password = os.getenv('SMTP_PASSWORD', '')
        sender = os.getenv('SMTP_FROM', '').strip()
        if not all((host, username, password, sender)):
            if os.getenv('APP_ENV') != 'Development':
                raise EmailConfigurationError('Dịch vụ email chưa được cấu hình')
            print(f'[LOCAL OTP] {address}: {code}', flush=True)
            return 'console'

        message = EmailMessage()
        message['Subject'] = 'Mã OTP xác thực - LeQuangHuy'
        message['From'] = sender
        message['To'] = address
        message.set_content(
            f'LeQuangHuy - Điểm danh sinh viên\n\n'
            f'Mã xác thực của bạn là: {code}\n\n'
            f'Mã có hiệu lực trong {minutes} phút.\n'
            'Nếu bạn không yêu cầu mã này, vui lòng bỏ qua email.'
        )
        with smtplib.SMTP(host, int(os.getenv('SMTP_PORT', '587')), timeout=15) as smtp:
            smtp.starttls(context=ssl.create_default_context())
            smtp.login(username, password)
            smtp.send_message(message)
        return 'email'
