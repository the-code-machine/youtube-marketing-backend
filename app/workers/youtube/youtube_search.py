from datetime import datetime, timezone
import requests
import time

BASE = "https://www.googleapis.com/youtube/v3/search"

def search_videos(api_key, backup_key, query, published_after=None, target_count=250):
    results = []
    next_page_token = None
    api_keys = [api_key, backup_key]
    current_key_index = 0
    
    # 1. Format Date
    formatted_date = None
    if published_after:
        if isinstance(published_after, int):
            published_after = datetime.fromtimestamp(published_after, tz=timezone.utc)
        if published_after.tzinfo is None:
            published_after = published_after.replace(tzinfo=timezone.utc)
        formatted_date = published_after.isoformat().replace("+00:00", "Z")

    # 2. Pagination Loop (The "1000 Leads" Fix)
    while len(results) < target_count and current_key_index < len(api_keys):
        active_key = api_keys[current_key_index]
        
        params = {
            "part": "snippet",
            "type": "video",
            "q": query,
            "order": "date",
            "maxResults": 50,
            "key": active_key,
            "regionCode": "IN", # Target India specifically
            "relevanceLanguage": "hi", # Target Hindi for Education
            "publishedAfter": formatted_date,
            "pageToken": next_page_token
        }

        try:
            resp = requests.get(BASE, params=params, timeout=30)

            if resp.status_code == 403:
                print(f"⚠️ Key {current_key_index + 1} exhausted. Rotating...")
                current_key_index += 1
                continue 

            if resp.status_code != 200: break

            data = resp.json()
            items = data.get("items", [])
            if not items: break

            for item in items:
                vid = item.get("id", {}).get("videoId")
                cid = item.get("snippet", {}).get("channelId")
                if vid and cid:
                    results.append({
                        "video_id": vid,
                        "channel_id": cid,
                        "published_at": item["snippet"]["publishedAt"]
                    })

            next_page_token = data.get("nextPageToken")
            if not next_page_token: break
            
            # Pause to respect rate limits
            time.sleep(0.2)

        except Exception as e:
            print(f"❌ Search Error: {e}")
            break

    return results, api_keys[current_key_index] if current_key_index < len(api_keys) else None