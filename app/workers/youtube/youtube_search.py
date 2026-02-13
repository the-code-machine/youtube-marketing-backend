from datetime import datetime, timezone
import requests

BASE = "https://www.googleapis.com/youtube/v3/search"

def search_videos(api_key, backup_key, query, published_after=None, max_pages=1):
    """
    Simplified rotation logic. 
    Attempts to fetch one page of 50 results. 
    If Key 1 is dead, it uses Key 2.
    """
    results = []
    api_keys = [api_key, backup_key]
    
    # 1. Format published_after for YouTube API
    formatted_date = None
    if published_after:
        if isinstance(published_after, int):
            published_after = datetime.fromtimestamp(published_after, tz=timezone.utc)
        elif isinstance(published_after, str):
            published_after = datetime.fromisoformat(published_after)
        
        if published_after.tzinfo is None:
            published_after = published_after.replace(tzinfo=timezone.utc)
        
        formatted_date = published_after.isoformat().replace("+00:00", "Z")

    # 2. Key Rotation Logic
    for index, active_key in enumerate(api_keys):
        params = {
            "part": "snippet",
            "type": "video",
            "q": query,
            "order": "date",
            "maxResults": 50,
            "key": active_key,
            "publishedAfter": formatted_date
        }

        try:
            resp = requests.get(BASE, params=params, timeout=30)

            # Check for Quota Error
            if resp.status_code == 403:
                print(f"⚠️ Key {index + 1} exhausted. Trying next...")
                continue # Try the next key in the list
            
            if resp.status_code != 200:
                print(f"❌ YouTube API Error ({resp.status_code}): {resp.text}")
                break # Stop if it's a different error (like invalid query)

            data = resp.json()
            items = data.get("items", [])

            for item in items:
                vid = item.get("id", {}).get("videoId")
                cid = item.get("snippet", {}).get("channelId")
                if vid and cid:
                    results.append({
                        "video_id": vid,
                        "channel_id": cid,
                        "published_at": item["snippet"]["publishedAt"]
                    })
            
            # If we successfully got data, return immediately
            if results or resp.status_code == 200:
                print(f"✅ Success with Key {index + 1}. Found {len(results)} videos.")
                return results ,active_key

        except Exception as e:
            print(f"❌ Request Exception with Key {index + 1}: {str(e)}")
            continue

    print("🚫 ALL API KEYS EXHAUSTED (Waiting for 1:30 PM IST reset).")
    return results