import requests
import re
import json
import time
from urllib.parse import urlparse, parse_qs, unquote
from concurrent.futures import ThreadPoolExecutor, as_completed
# REMOVE the old clean_email function entirely, replace import:
from app.workers.youtube.email_validator import clean_email
HEADERS = {
    "User-Agent": "Mozilla/5.0"
}

SOCIAL_DOMAINS = [
    "instagram.com",
    "facebook.com",
    "twitter.com",
    "x.com",
    "tiktok.com",
    "linktr.ee",
    "beacons.ai",
    "spotify.com",
    "soundcloud.com"
]

EMAIL_REGEX = r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"

BAD_PATTERNS = [
    "...",
    "/share",
    "youtube.com",
    "google.com"
]


# ---------------- REDIRECT UNWRAPPER ----------------

def unwrap_youtube_redirect(url):

    if "youtube.com/redirect" not in url:
        return url

    try:
        qs = parse_qs(urlparse(url).query)
        if "q" in qs:
            return unquote(qs["q"][0])
    except:
        pass

    return url


# ---------------- SOCIAL NORMALIZER ----------------

def normalize_social(url):

    try:
        url = url.replace("\\n", "").strip()
        url = unwrap_youtube_redirect(url)

        parsed = urlparse(url)

        if not parsed.scheme or not parsed.netloc:
            return None

        domain = parsed.netloc.lower().replace("www.", "")
        path = parsed.path.strip("/")

        clean = f"{parsed.scheme}://{domain}/{path}".split("?")[0].rstrip("/")

        # Instagram
        if "instagram.com" in clean:
            parts = clean.split("/")
            if len(parts) >= 4:
                clean = f"https://instagram.com/{parts[3]}"

        # Facebook
        if "facebook.com" in clean:
            parts = clean.split("/")
            if len(parts) >= 4:
                clean = f"https://facebook.com/{parts[3]}"

        # Remove root garbage
        if clean in ["https://instagram.com", "https://facebook.com"]:
            return None

        for bad in BAD_PATTERNS:
            if bad in clean:
                return None

        return clean.rstrip("/")

    except:
        return None


# ---------------- YT DATA EXTRACT ----------------

def _extract_yt_initial_data(html):

    m = re.search(r"var ytInitialData = (.*?);</script>", html)

    if not m:
        return None

    try:
        return json.loads(m.group(1))
    except:
        return None




# ---------------- MAIN SCRAPER ----------------

def scrape_about(channel_id, videos_raw=None):

    url = f"https://www.youtube.com/channel/{channel_id}/about"

    try:
        r = requests.get(url, headers=HEADERS, timeout=20)

        if r.status_code != 200:
            return [], None

        data = _extract_yt_initial_data(r.text)
        if not data:
            return [], None

        raw = json.dumps(data)

        # Merge video descriptions for better email hit
        if videos_raw:
            for v in videos_raw:
                raw += " " + v["snippet"].get("description", "")

        links = set()

        for domain in SOCIAL_DOMAINS:
            found = re.findall(r"https?://[^\s\"']*" + re.escape(domain) + "[^\s\"']*", raw)

            for f in found:
                norm = normalize_social(f)
                if norm:
                    links.add(norm)

        # EMAIL EXTRACTION
        email = None
        emails = re.findall(EMAIL_REGEX, raw)

        for e in emails:
            cleaned = clean_email(e)
            if cleaned:
                email = cleaned
                break

        time.sleep(0.2)

        return list(links), email

    except Exception as e:
        print("About scrape failed:", channel_id, e)
        return [], None



def scrape_all_about(channel_ids):

    results = {}

    with ThreadPoolExecutor(max_workers=10) as executor:

        futures = {
            executor.submit(scrape_about, cid): cid
            for cid in channel_ids
        }

        for future in as_completed(futures):

            cid = futures[future]

            try:
                links, email = future.result()
                results[cid] = {
                    "links": links,
                    "email": email
                }
            except Exception:
                results[cid] = {
                    "links": [],
                    "email": None
                }

    return results
