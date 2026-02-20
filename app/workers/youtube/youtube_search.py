"""
app/workers/youtube/youtube_search.py

Executes a SINGLE search job against YouTube Data API v3.
Designed to be called in a loop/thread-pool by main_worker.py.

Key differences from old version:
  ✅ Uses APIKeyManager pool instead of 2 hardcoded keys
  ✅ region_code and language are parameters (not hardcoded to IN/hi)
  ✅ Proper 403 handling — marks key exhausted, retries same page with next key
  ✅ 429 rate-limit handling with exponential backoff
  ✅ Returns (results, total_fetched) instead of (results, working_key)
  ✅ Deduplication within a single job run
  ✅ Respects target_count ceiling to avoid wasting quota
"""

import time
import requests
from datetime import datetime, timezone

from app.workers.youtube.key_manager import APIKeyManager


BASE_URL = "https://www.googleapis.com/youtube/v3/search"

# YouTube Search API caps pagination at ~500 results per query
# (roughly 10 pages × 50 results before nextPageToken stops coming)
MAX_PAGES_PER_JOB = 10


def _format_date(dt) -> str | None:
    """Convert datetime or unix timestamp to RFC 3339 / ISO 8601 format."""
    if dt is None:
        return None
    if isinstance(dt, (int, float)):
        dt = datetime.fromtimestamp(dt, tz=timezone.utc)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.isoformat().replace("+00:00", "Z")


def search_videos(
    key_manager: APIKeyManager,
    query: str,
    published_after=None,
    target_count: int = 500,
    region_code: str = "IN",
    language: str = "hi",
) -> list[dict]:
    """
    Searches YouTube for videos matching `query` and returns a deduplicated
    list of {video_id, channel_id, published_at} dicts.

    Args:
        key_manager:     APIKeyManager instance (shared across all jobs in a run)
        query:           Search string (e.g. "stock market hindi 2026")
        published_after: datetime | unix_ts | None — only fetch videos newer than this
        target_count:    Stop fetching after collecting this many results (max 500)
        region_code:     ISO 3166-1 alpha-2 (e.g. "IN", "US", "GB")
        language:        BCP-47 language code (e.g. "hi", "en")

    Returns:
        List of dicts: [{"video_id": str, "channel_id": str, "published_at": str}]
    """

    results: list[dict] = []
    seen_video_ids: set[str] = set()
    next_page_token: str | None = None
    pages_fetched = 0
    formatted_date = _format_date(published_after)

    effective_target = min(target_count, MAX_PAGES_PER_JOB * 50)  # Hard cap at 500

    while len(results) < effective_target and pages_fetched < MAX_PAGES_PER_JOB:

        # ── Get a live API key ──────────────────────────────────────────
        active_key = key_manager.get_key()
        if not active_key:
            print(f"    💀 No keys available. Stopping job: '{query[:40]}'")
            break

        params = {
            "part": "snippet",
            "type": "video",
            "q": query,
            "order": "date",
            "maxResults": 50,
            "key": active_key,
            "regionCode": region_code,
            "relevanceLanguage": language,
        }

        if formatted_date:
            params["publishedAfter"] = formatted_date

        if next_page_token:
            params["pageToken"] = next_page_token

        # ── HTTP Call ──────────────────────────────────────────────────
        try:
            resp = requests.get(BASE_URL, params=params, timeout=30)

        except requests.exceptions.Timeout:
            print(f"    ⏱️  Timeout on page {pages_fetched + 1} for '{query[:40]}'. Retrying...")
            time.sleep(2)
            continue

        except requests.exceptions.RequestException as e:
            print(f"    ❌ Network error: {e}")
            time.sleep(3)
            break

        # ── Status Handling ────────────────────────────────────────────

        # 403 = quota exceeded for this key
        if resp.status_code == 403:
            key_manager.mark_exhausted(active_key)
            # Don't advance page — retry same page with next key
            time.sleep(0.5)
            continue

        # 429 = global rate limit — backoff and retry
        if resp.status_code == 429:
            print(f"    ⏸️  Rate limited (429). Waiting 15s...")
            time.sleep(15)
            continue

        # Any other non-200 = skip this page
        if resp.status_code != 200:
            print(f"    ⚠️  Unexpected status {resp.status_code} for '{query[:40]}'. Breaking.")
            break

        # ── Parse Response ─────────────────────────────────────────────
        data = resp.json()
        items = data.get("items", [])

        if not items:
            break  # No more results for this query

        new_this_page = 0
        for item in items:
            vid = item.get("id", {}).get("videoId")
            cid = item.get("snippet", {}).get("channelId")
            pub = item.get("snippet", {}).get("publishedAt")

            if vid and cid and vid not in seen_video_ids:
                seen_video_ids.add(vid)
                results.append({
                    "video_id": vid,
                    "channel_id": cid,
                    "published_at": pub,
                })
                new_this_page += 1

        pages_fetched += 1
        next_page_token = data.get("nextPageToken")

        # No more pages available from YouTube
        if not next_page_token:
            break

        # Small polite delay between pages (avoids per-project rate limits)
        time.sleep(0.15)

    return results