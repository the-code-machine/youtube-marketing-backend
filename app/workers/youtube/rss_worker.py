"""
app/workers/youtube/rss_worker.py

PRIMARY DISCOVERY via YouTube RSS Feeds
════════════════════════════════════════

WHY RSS FIRST:
  - Official YouTube public feed — no API key needed
  - Zero quota consumption
  - Zero ban risk — it's the same feed your RSS reader uses
  - Returns newest videos per query in real-time
  - Can make unlimited requests (be polite — add delays)

WHAT RSS GIVES YOU:
  - video_id
  - channel_id
  - video title
  - published_at
  - channel name

WHAT RSS DOESN'T GIVE (needs API enrichment):
  - subscriber count
  - view count
  - channel description / email
  - video tags

FLOW:
  1. RSS Worker    → discovers video_ids + channel_ids (free)
  2. API Enricher  → fetches details for NEW channels only (quota-efficient)
  3. About Scraper → emails/socials (no API needed)

QUOTA SAVINGS:
  Old approach: 400 search jobs × 200 units = 80,000 units/run
  New approach: 0 units for discovery
                ~50 units for enriching new channels (channels.list)
                Savings: 99.9% quota reduction ✅
"""

import feedparser
import requests
import time
import re
from datetime import datetime, timezone, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import quote_plus

# ─────────────────────────────────────────────────────────────────────────────
# RSS FEED URLS
# ─────────────────────────────────────────────────────────────────────────────

RSS_SEARCH_BASE = "https://www.youtube.com/feeds/videos.xml?search_query={query}"
RSS_CHANNEL_BASE = "https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; RSS Reader/1.0)",
    "Accept": "application/rss+xml, application/xml, text/xml",
}


# ─────────────────────────────────────────────────────────────────────────────
# SEARCH QUERIES FOR RSS
# Same as search_matrix but flattened — RSS ignores region/language params
# so we just need the query strings
# ─────────────────────────────────────────────────────────────────────────────

RSS_QUERIES = {
    "Music Creators": [
        "official music video 2026",
        "new song 2026",
        "new single official video",
        "indie artist music video",
        "hip hop music video 2026",
        "afrobeats music video 2026",
        "punjabi song 2026",
        "hindi song 2026",
        "bollywood song new",
        "latin music video 2026",
    ],
    "Podcast Creators": [
        "podcast episode 2026",
        "business podcast new episode",
        "entrepreneur interview podcast",
        "self improvement podcast new",
        "technology podcast new episode",
        "comedy podcast new episode",
        "hindi podcast episode",
        "startup india podcast",
    ],
    "Finance & Investing": [
        "stock market investing 2026",
        "investing for beginners",
        "personal finance tips new",
        "crypto trading tutorial 2026",
        "passive income strategy",
        "trading tutorial beginners",
        "stock market hindi 2026",
        "mutual fund india hindi",
    ],
    "Education & Tech": [
        "coding tutorial beginner 2026",
        "python tutorial beginners",
        "web development tutorial",
        "data science tutorial",
        "machine learning tutorial",
        "javascript tutorial beginners",
        "ai tools tutorial 2026",
        "tech career advice",
    ],
    "Gaming Creators": [
        "gaming channel new video 2026",
        "lets play gameplay 2026",
        "game review new release",
        "minecraft gameplay 2026",
        "roblox new video 2026",
        "mobile gaming gameplay new",
        "esports highlights new video",
    ],
    "Fitness & Health": [
        "workout tutorial beginner 2026",
        "home workout no equipment",
        "weight loss workout beginner",
        "gym workout routine new",
        "yoga for beginners new",
        "hiit workout tutorial",
    ],
    "Food & Cooking": [
        "cooking tutorial easy recipe",
        "recipe video beginner cooking",
        "food vlog new video",
        "street food tour new",
        "meal prep beginner guide",
        "healthy recipes easy cooking",
    ],
    "Comedy & Entertainment": [
        "comedy skit funny video 2026",
        "stand up comedy new video",
        "funny prank video 2026",
        "sketch comedy new video",
        "reaction video new 2026",
        "web series new episode 2026",
    ],
    "Business & Entrepreneurship": [
        "how to start a business 2026",
        "entrepreneur vlog new",
        "online business tutorial new",
        "side hustle ideas new",
        "passive income strategy new",
        "ecommerce business tutorial",
    ],
    "Lifestyle & Travel Vlogs": [
        "travel vlog new video 2026",
        "day in my life vlog new",
        "digital nomad vlog 2026",
        "lifestyle vlog daily routine",
        "budget travel vlog new",
        "solo travel vlog new",
    ],
}


# ─────────────────────────────────────────────────────────────────────────────
# CORE RSS FETCHER
# ─────────────────────────────────────────────────────────────────────────────

def _parse_video_id(entry_id: str) -> str | None:
    """Extract video ID from RSS entry ID like yt:video:dQw4w9WgXcQ"""
    match = re.search(r"yt:video:([A-Za-z0-9_-]{11})", entry_id)
    return match.group(1) if match else None


def _parse_channel_id(entry) -> str | None:
    """Extract channel ID from RSS entry."""
    # Try yt:channelId tag first
    channel_id = getattr(entry, "yt_channelid", None)
    if channel_id:
        return channel_id
    # Fallback: extract from author_detail url
    author_url = getattr(entry, "author_detail", {}).get("href", "")
    match = re.search(r"channel/([A-Za-z0-9_-]+)", author_url)
    return match.group(1) if match else None


def fetch_rss_query(query: str, category_name: str, published_after: datetime = None) -> list[dict]:
    """
    Fetches YouTube RSS feed for a search query.
    Returns up to 15 latest videos (YouTube RSS limit per query).
    """
    url = RSS_SEARCH_BASE.format(query=quote_plus(query))

    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)

        if resp.status_code != 200:
            return []

        feed = feedparser.parse(resp.content)
        results = []

        for entry in feed.entries:
            video_id = _parse_video_id(entry.get("id", ""))
            channel_id = _parse_channel_id(entry)

            if not video_id or not channel_id:
                continue

            # Parse published date
            published_str = entry.get("published", "")
            try:
                published_dt = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
            except Exception:
                published_dt = datetime.utcnow().replace(tzinfo=timezone.utc)

            # Filter by published_after if given
            if published_after:
                if published_after.tzinfo is None:
                    published_after = published_after.replace(tzinfo=timezone.utc)
                if published_dt < published_after:
                    continue

            results.append({
                "video_id": video_id,
                "channel_id": channel_id,
                "title": entry.get("title", ""),
                "published_at": published_dt.isoformat(),
                "category_name": category_name,
                "source": "rss",
            })

        return results

    except Exception as e:
        print(f"   ⚠️  RSS fetch failed [{query[:30]}]: {e}")
        return []


def fetch_rss_channel(channel_id: str) -> list[dict]:
    """
    Fetches latest videos from a specific channel via RSS.
    Used to monitor known channels for new uploads.
    Returns up to 15 latest videos.
    """
    url = RSS_CHANNEL_BASE.format(channel_id=channel_id)

    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        if resp.status_code != 200:
            return []

        feed = feedparser.parse(resp.content)
        results = []

        for entry in feed.entries:
            video_id = _parse_video_id(entry.get("id", ""))
            if not video_id:
                continue

            try:
                published_dt = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
            except Exception:
                published_dt = datetime.utcnow().replace(tzinfo=timezone.utc)

            results.append({
                "video_id": video_id,
                "channel_id": channel_id,
                "title": entry.get("title", ""),
                "published_at": published_dt.isoformat(),
                "source": "rss_channel",
            })

        return results

    except Exception as e:
        return []


# ─────────────────────────────────────────────────────────────────────────────
# MAIN DISCOVERY FUNCTION
# ─────────────────────────────────────────────────────────────────────────────

def discover_via_rss(
    category_name: str,
    published_after: datetime = None,
    threads: int = 10,
) -> list[dict]:
    """
    Runs all RSS queries for a category in parallel.
    Returns deduplicated list of {video_id, channel_id, published_at}.

    Args:
        category_name:   Must match key in RSS_QUERIES
        published_after: Only return videos newer than this datetime
        threads:         Parallel fetch threads (keep ≤15 to be polite)
    """
    queries = RSS_QUERIES.get(category_name, [])
    if not queries:
        print(f"   ⚠️  No RSS queries for '{category_name}'")
        return []

    if published_after is None:
        published_after = datetime.utcnow().replace(tzinfo=timezone.utc) - timedelta(hours=26)

    print(f"   📡 RSS: {len(queries)} queries for '{category_name}'...")

    all_results = []
    seen_video_ids = set()

    with ThreadPoolExecutor(max_workers=threads) as executor:
        futures = {
            executor.submit(fetch_rss_query, q, category_name, published_after): q
            for q in queries
        }
        for future in as_completed(futures):
            try:
                batch = future.result()
                for item in batch:
                    if item["video_id"] not in seen_video_ids:
                        seen_video_ids.add(item["video_id"])
                        all_results.append(item)
            except Exception as e:
                pass
            # Small polite delay
            time.sleep(0.05)

    print(f"   ✅  RSS discovered: {len(all_results)} unique videos")
    return all_results


def monitor_known_channels(channel_ids: list[str], published_after: datetime = None, threads: int = 20) -> list[dict]:
    """
    Monitors already-known channels for NEW video uploads via RSS.
    This is ZERO quota — perfect for re-checking channels we already have in DB.
    
    Use case: Check your existing 15,000 channels for new uploads every 8 hours.
    """
    if published_after is None:
        published_after = datetime.utcnow().replace(tzinfo=timezone.utc) - timedelta(hours=26)

    print(f"   📡 Monitoring {len(channel_ids):,} known channels via RSS...")

    all_results = []
    seen = set()

    with ThreadPoolExecutor(max_workers=threads) as executor:
        futures = {
            executor.submit(fetch_rss_channel, cid): cid
            for cid in channel_ids
        }
        for future in as_completed(futures):
            try:
                batch = future.result()
                for item in batch:
                    pub = datetime.fromisoformat(item["published_at"])
                    if pub.tzinfo is None:
                        pub = pub.replace(tzinfo=timezone.utc)
                    after = published_after
                    if after.tzinfo is None:
                        after = after.replace(tzinfo=timezone.utc)
                    if pub >= after and item["video_id"] not in seen:
                        seen.add(item["video_id"])
                        all_results.append(item)
            except Exception:
                pass
            time.sleep(0.02)

    print(f"   ✅  Known channel monitoring: {len(all_results):,} new videos found")
    return all_results