import re
from app.workers.youtube.email_validator import is_valid_email
EMAIL = r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+"

SOCIALS = {
    "instagram": r"(https?:\/\/(www\.)?instagram\.com\/[A-Za-z0-9_.]+)",
    "twitter": r"(https?:\/\/(www\.)?twitter\.com\/[A-Za-z0-9_.]+)",
    "tiktok": r"(https?:\/\/(www\.)?tiktok\.com\/@[A-Za-z0-9_.]+)",
    "facebook": r"(https?:\/\/(www\.)?facebook\.com\/[A-Za-z0-9_.]+)",
    "youtube": r"(https?:\/\/(www\.)?youtube\.com\/[^\s]+)",
}

URL = r"(https?:\/\/[^\s]+)"

def extract_emails(text):
    raw = list(set(re.findall(EMAIL, text or "")))
    return [e.lower() for e in raw if is_valid_email(e)]


def extract_socials(text):

    found = []

    for platform, regex in SOCIALS.items():
        matches = re.findall(regex, text or "")
        for m in matches:
            found.append((platform, m[0]))

    for site in re.findall(URL, text or ""):
        if "instagram" not in site and "facebook" not in site:
            found.append(("website", site))

    return found
