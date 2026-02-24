import requests
import json
from app.core.config import settings
import logging

logger = logging.getLogger(__name__)

# Error messages that mean the recipient address doesn't exist
RECIPIENT_NOT_FOUND_ERRORS = [
    "550",
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
        self.api_url = settings.ZEPTO_API_URL
        self.api_key = settings.ZEPTO_API_KEY
        self.from_address = settings.ZEPTO_FROM_ADDRESS

    def send_email(self, to_email: str, subject: str, body: str):
        try:
            payload = json.dumps({
                "from": {"address": self.from_address},
                "to": [{"email_address": {"address": to_email}}],
                "subject": subject,
                "htmlbody": body
            })

            headers = {
                "accept": "application/json",
                "content-type": "application/json",
                "authorization": self.api_key
            }

            response = requests.post(self.api_url, data=payload, headers=headers)

            # ZeptoMail returns error details in JSON body even on failure
            response_data = response.json()

            if response.status_code == 200:
                return True, None

            # Parse ZeptoMail error response
            error_message = str(response_data).lower()

            # Check if it's a recipient-not-found type error
            if any(err in error_message for err in RECIPIENT_NOT_FOUND_ERRORS) or response.status_code in (422, 400):
                logger.warning(f"📭 Recipient not found / rejected: {to_email} — {response_data}")
                return False, f"RECIPIENT_NOT_FOUND: {response_data}"

            logger.error(f"❌ ZeptoMail error for {to_email}: {response_data}")
            return False, str(response_data)

        except requests.exceptions.ConnectionError as e:
            logger.error(f"🔌 Connection error while sending to {to_email}: {e}")
            return False, f"CONNECTION_ERROR: {e}"

        except requests.exceptions.Timeout as e:
            logger.error(f"⏱️ Timeout while sending to {to_email}: {e}")
            return False, f"TIMEOUT_ERROR: {e}"

        except requests.exceptions.HTTPError as e:
            error_msg = str(e).lower()
            if any(err in error_msg for err in RECIPIENT_NOT_FOUND_ERRORS):
                logger.warning(f"📭 Address likely invalid: {to_email}")
                return False, f"RECIPIENT_NOT_FOUND: {e}"
            logger.error(f"❌ HTTP error for {to_email}: {e}")
            return False, str(e)

        except Exception as e:
            logger.error(f"❌ Failed to send email to {to_email}: {e}")
            return False, str(e)