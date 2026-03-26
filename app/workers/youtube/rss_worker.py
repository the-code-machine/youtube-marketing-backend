"""
app/workers/youtube/rss_worker.py

Channel-based RSS monitoring — the ONLY RSS that YouTube still supports.

CONFIRMED DEAD (returns 400):
  https://www.youtube.com/feeds/videos.xml?search_query=...
  YouTube killed search RSS feeds years ago.

CONFIRMED WORKING:
  https://www.youtube.com/feeds/videos.xml?channel_id=UCxxxxxx
  Returns latest 15 videos per channel. Zero API units. Official.

USAGE:
  This file provides monitor_known_channels() only.
  New channel DISCOVERY is handled by API search in main_worker.
  This file handles UPDATE monitoring of channels already in DB.
"""

import re
import time
import requests
from datetime import datetime, timezone, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed

try:
    import feedparser
    FEEDPARSER_AVAILABLE = True
except ImportError:
    FEEDPARSER_AVAILABLE = False
    print("⚠️  feedparser not installed. Run: pip install feedparser --break-system-packages")


CHANNEL_RSS_BASE = "https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; RSS Reader/1.0)",
    "Accept": "application/rss+xml, application/xml, text/xml",
}


# ─────────────────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def _parse_video_id(entry_id: str) -> str | None:
    """Extract video ID from RSS entry ID like yt:video:dQw4w9WgXcQ"""
    match = re.search(r"yt:video:([A-Za-z0-9_-]{11})", entry_id)
    return match.group(1) if match else None


def _parse_channel_id(entry) -> str | None:
    """Extract channel ID from RSS entry."""
    channel_id = getattr(entry, "yt_channelid", None)
    if channel_id:
        return channel_id
    author_url = getattr(entry, "author_detail", {}).get("href", "")
    match = re.search(r"channel/([A-Za-z0-9_-]+)", author_url)
    return match.group(1) if match else None


def _to_utc(dt) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


# ─────────────────────────────────────────────────────────────────────────────
# SINGLE CHANNEL FETCH
# ─────────────────────────────────────────────────────────────────────────────

def fetch_channel_rss(channel_id: str, published_after: datetime = None) -> list[dict]:
    """
    Fetches latest videos for ONE channel via RSS.
    Returns up to 15 results (YouTube RSS hard limit per channel).
    Zero API units consumed.
    """
    if not FEEDPARSER_AVAILABLE:
        return []

    url = CHANNEL_RSS_BASE.format(channel_id=channel_id)

    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        if resp.status_code != 200:
            return []

        feed = feedparser.parse(resp.content)
        results = []

        for entry in feed.entries:
            video_id  = _parse_video_id(entry.get("id", ""))
            cid       = _parse_channel_id(entry) or channel_id

            if not video_id:
                continue

            try:
                published_dt = _to_utc(datetime(*entry.published_parsed[:6]))
            except Exception:
                published_dt = datetime.utcnow().replace(tzinfo=timezone.utc)

            if published_after:
                after = _to_utc(published_after) if published_after.tzinfo is None else published_after
                if published_dt < after:
                    continue

            results.append({
                "video_id":    video_id,
                "channel_id":  cid,
                "title":       entry.get("title", ""),
                "published_at": published_dt.isoformat(),
                "source":      "rss_channel",
            })

        return results

    except Exception as e:
        return []


# ─────────────────────────────────────────────────────────────────────────────
# BULK CHANNEL MONITOR
# ─────────────────────────────────────────────────────────────────────────────

def monitor_known_channels(
    channel_ids: list[str],
    published_after: datetime = None,
    threads: int = 20,
) -> list[dict]:
    """
    Monitors a list of known channels for NEW video uploads via RSS.
    Zero API units — uses channel feed URL only.

    Called every run to catch new uploads from channels already in DB.
    Scales to thousands of channels efficiently via threading.

    Args:
        channel_ids:     List of YouTube channel IDs to check
        published_after: Only return videos newer than this datetime
        threads:         Parallel fetch threads (20 is safe and fast)

    Returns:
        Deduplicated list of {video_id, channel_id, title, published_at}
    """
    if not channel_ids:
        return []

    if not FEEDPARSER_AVAILABLE:
        print("⚠️  feedparser not installed — channel RSS monitoring skipped")
        return []

    if published_after is None:
        published_after = datetime.utcnow().replace(tzinfo=timezone.utc) - timedelta(hours=26)

    print(f"   📡 Channel RSS monitor: checking {len(channel_ids):,} channels ({threads} threads)...")

    all_results = []
    seen_ids    = set()

    with ThreadPoolExecutor(max_workers=threads) as executor:
        futures = {
            executor.submit(fetch_channel_rss, cid, published_after): cid
            for cid in channel_ids
        }
        for future in as_completed(futures):
            try:
                for item in future.result():
                    if item["video_id"] not in seen_ids:
                        seen_ids.add(item["video_id"])
                        all_results.append(item)
            except Exception:
                pass
            time.sleep(0.01)

    print(f"   ✅  Channel RSS: {len(all_results):,} new videos found")
    return all_results