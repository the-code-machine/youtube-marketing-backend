import re

# -------------------------------------------------------
# BLACKLIST DICTIONARY
# -------------------------------------------------------

# Fake/sample/placeholder local parts
BLACKLISTED_LOCAL_PARTS = {
    "sample", "example", "test", "noreply", "no-reply",
    "donotreply", "info", "admin", "support", "hello",
    "contact", "email", "user", "dummy", "fake", "spam",
    "mail", "webmaster", "postmaster", "sales", "marketing",
    "help", "abc", "xyz", "demo"
}

# Fake/placeholder domains
BLACKLISTED_DOMAINS = {
    "example.com", "example.org", "example.net",
    "test.com", "test.org",
    "domain.com", "yourdomain.com", "yoursite.com",
    "website.com", "email.com", "myemail.com",
    "gmail.con", "gamil.com", "gmal.com",  # Common typos
    "hotmail.con", "yaho.com", "yahooo.com",
    "tempmail.com", "mailinator.com", "guerrillamail.com",
    "10minutemail.com", "throwaway.com", "fakeinbox.com",
    "dispostable.com", "trashmail.com", "sharklasers.com",
}

# Valid TLDs that must appear at end of domain (min check)
# At least 2 chars, max 6 chars is a reasonable rule
TLD_REGEX = re.compile(r"\.[a-zA-Z]{2,6}$")

# Full strict email regex
STRICT_EMAIL_REGEX = re.compile(
    r"^[a-zA-Z0-9][a-zA-Z0-9_.+-]*"   # local part: must start with alphanum
    r"@"
    r"[a-zA-Z0-9-]+"                   # domain name
    r"(\.[a-zA-Z0-9-]+)*"              # subdomains
    r"\.[a-zA-Z]{2,6}$"               # valid TLD
)

def is_valid_email(raw: str) -> bool:
    """
    Full validation pipeline:
    1. Regex structure check
    2. Blacklisted domain check
    3. Blacklisted local part check
    4. Extra sanity checks
    """
    if not raw or not isinstance(raw, str):
        return False

    email = raw.strip().lower()

    # Must have exactly one @
    parts = email.split("@")
    if len(parts) != 2:
        return False

    local, domain = parts[0], parts[1]

    # 1. Regex structure — catches "u2068@dr.poojakvlogs" (no proper TLD)
    if not STRICT_EMAIL_REGEX.match(email):
        return False

    # 2. Domain blacklist
    if domain in BLACKLISTED_DOMAINS:
        return False

    # 3. Local part blacklist
    if local in BLACKLISTED_LOCAL_PARTS:
        return False

    # 4. Extra sanity
    if len(local) < 2:           # too short local part
        return False
    if len(domain) < 4:          # too short domain
        return False
    if domain.endswith((".png", ".jpg", ".jpeg", ".webp", ".gif")):
        return False

    return True


def clean_email(raw: str):
    """Drop-in replacement for the old clean_email()."""
    if is_valid_email(raw):
        return raw.strip().lower()
    return None