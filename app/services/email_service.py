import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from app.core.config import settings
import logging

logger = logging.getLogger(__name__)

class EmailService:
    def __init__(self):
        self.server = settings.SMTP_SERVER
        self.port = settings.SMTP_PORT
        self.user = settings.SMTP_USER
        self.password = settings.SMTP_PASSWORD

    def send_email(self, to_email: str, subject: str, body: str):
        """
        Sends a single email using SMTP.
        Returns (True, None) on success, or (False, error_message) on failure.
        """
        try:
            msg = MIMEMultipart()
            msg["From"] = self.user
            msg["To"] = to_email
            msg["Subject"] = subject

            # Attach body as HTML (better for templates)
            msg.attach(MIMEText(body, "html"))

            # Connect & Send
            # Note: For production volume, we'd keep the connection open. 
            # For 100/day, opening/closing per batch is safer and cleaner.
            with smtplib.SMTP(self.server, self.port) as server:
                server.starttls()
                server.login(self.user, self.password)
                server.sendmail(self.user, to_email, msg.as_string())
            
            return True, None

        except Exception as e:
            logger.error(f"Failed to send email to {to_email}: {e}")
            return False, str(e)