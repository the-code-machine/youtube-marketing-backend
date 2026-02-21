import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from app.core.config import settings
import logging

logger = logging.getLogger(__name__)

# Error messages that mean the recipient address doesn't exist
RECIPIENT_NOT_FOUND_ERRORS = [
    "550",                          # Standard reject
    "user unknown",
    "does not exist",
    "no such user",
    "invalid address",
    "address not found",
    "recipient rejected",
    "mailbox unavailable",
]

class EmailService:
    def __init__(self):
        self.server = settings.SMTP_SERVER
        self.port = settings.SMTP_PORT
        self.user = settings.SMTP_USER
        self.password = settings.SMTP_PASSWORD

    def send_email(self, to_email: str, subject: str, body: str):
        try:
            msg = MIMEMultipart()
            msg["From"] = self.user
            msg["To"] = to_email
            msg["Subject"] = subject
            msg.attach(MIMEText(body, "html"))

            with smtplib.SMTP(self.server, self.port) as server:
                server.starttls()
                server.login(self.user, self.password)
                server.sendmail(self.user, to_email, msg.as_string())

            return True, None

        except smtplib.SMTPRecipientsRefused as e:
            # Gmail-specific: recipient address rejected/not found
            error_msg = str(e).lower()
            logger.warning(f"📭 Recipient not found / rejected: {to_email} — {e}")
            return False, f"RECIPIENT_NOT_FOUND: {e}"

        except smtplib.SMTPAuthenticationError as e:
            logger.error(f"🔐 SMTP Auth failed — check your Gmail App Password: {e}")
            return False, f"AUTH_ERROR: {e}"

        except smtplib.SMTPException as e:
            error_msg = str(e).lower()
            # Check if it's a soft "address not found" type error
            if any(err in error_msg for err in RECIPIENT_NOT_FOUND_ERRORS):
                logger.warning(f"📭 Address likely invalid: {to_email}")
                return False, f"RECIPIENT_NOT_FOUND: {e}"
            logger.error(f"❌ SMTP error for {to_email}: {e}")
            return False, str(e)

        except Exception as e:
            logger.error(f"❌ Failed to send email to {to_email}: {e}")
            return False, str(e)