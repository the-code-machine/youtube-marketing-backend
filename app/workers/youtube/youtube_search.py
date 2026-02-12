from datetime import datetime, timezone
import requests
import time

BASE = "https://www.googleapis.com/youtube/v3/search"

def search_videos(api_key, query, published_after=None, max_pages=1):
    """
    Optimized search with pagination.
    max_pages=1: Costs 100 units. Use this to run hourly for 4 categories (9,600 units/day).
    max_pages=5: Costs 500 units. Use this for deeper, less frequent crawls.
    """
    results = []
    next_page_token = None
    
    # 1. Format published_after for YouTube API (RFC 3339)
    formatted_date = None
    if published_after:
        if isinstance(published_after, int):
            published_after = datetime.fromtimestamp(published_after, tz=timezone.utc)
        elif isinstance(published_after, str):
            published_after = datetime.fromisoformat(published_after)
        
        if published_after.tzinfo is None:
            published_after = published_after.replace(tzinfo=timezone.utc)
        
        formatted_date = published_after.isoformat().replace("+00:00", "Z")

    # 2. Pagination Loop
    for page_num in range(max_pages):
        params = {
            "part": "snippet",
            "type": "video",
            "q": query,
            "order": "date",
            "maxResults": 50,  # ALWAYS 50 to maximize value per 100 units
            "key": api_key,
            "publishedAfter": formatted_date,
            "pageToken": next_page_token
        }

        try:
            resp = requests.get(BASE, params=params, timeout=30)

            if resp.status_code != 200:
                print(f"❌ YouTube search failed: {resp.text}")
                break

            data = resp.json()
            items = data.get("items", [])

            if not items:
                print(f"ℹ️ No more items found on page {page_num + 1}")
                break

            for item in items:
                vid = item.get("id", {}).get("videoId")
                cid = item.get("snippet", {}).get("channelId")

                if vid and cid:
                    results.append({
                        "video_id": vid,
                        "channel_id": cid,
                        "published_at": item["snippet"]["publishedAt"]
                    })

            # 3. Handle Next Page
            next_page_token = data.get("nextPageToken")
            if not next_page_token:
                break
            
            # Optional small sleep to avoid rate limiting
            time.sleep(0.1)

        except Exception as e:
            print(f"❌ Search exception on page {page_num + 1}: {str(e)}")
            break

    print(f"✅ Search complete. Fetched {len(results)} videos across {page_num + 1} pages.")
    return results