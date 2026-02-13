from datetime import datetime, timezone
import requests
import time

BASE = "https://www.googleapis.com/youtube/v3/search"

def search_videos(api_key, backup_key, query, published_after=None, max_pages=1):
    results = []
    next_page_token = None
    
    # 1. Store keys in a list for easy rotation
    api_keys = [api_key, backup_key]
    current_key_index = 0

    # 2. Format published_after for YouTube API (RFC 3339)
    formatted_date = None
    if published_after:
        if isinstance(published_after, int):
            published_after = datetime.fromtimestamp(published_after, tz=timezone.utc)
        elif isinstance(published_after, str):
            published_after = datetime.fromisoformat(published_after)
        
        if published_after.tzinfo is None:
            published_after = published_after.replace(tzinfo=timezone.utc)
        
        formatted_date = published_after.isoformat().replace("+00:00", "Z")

    # 3. Pagination Loop
    for page_num in range(max_pages):
        # We use a while loop inside to allow retrying the SAME page if a key fails
        success = False
        while not success and current_key_index < len(api_keys):
            active_key = api_keys[current_key_index]
            
            params = {
                "part": "snippet",
                "type": "video",
                "q": query,
                "order": "date",
                "maxResults": 50,
                "key": active_key,
                "publishedAfter": formatted_date,
                "pageToken": next_page_token
            }

            try:
                resp = requests.get(BASE, params=params, timeout=30)

                # Handle Quota Exceeded
                if resp.status_code == 403:
                    print(f"⚠️ Key {current_key_index + 1} exhausted (Quota Exceeded). Rotating...")
                    current_key_index += 1
                    continue # Retry the 'while' loop with the next key
                
                if resp.status_code != 200:
                    print(f"❌ YouTube search failed ({resp.status_code}): {resp.text}")
                    return results # Stop completely if it's a non-quota error

                data = resp.json()
                items = data.get("items", [])

                if not items:
                    print(f"ℹ️ No more items found on page {page_num + 1}")
                    return results

                for item in items:
                    vid = item.get("id", {}).get("videoId")
                    cid = item.get("snippet", {}).get("channelId")
                    if vid and cid:
                        results.append({
                            "video_id": vid,
                            "channel_id": cid,
                            "published_at": item["snippet"]["publishedAt"]
                        })

                # Handle Pagination
                next_page_token = data.get("nextPageToken")
                success = True # Move to the next page in the 'for' loop
                
                if not next_page_token:
                    return results
                
                time.sleep(0.1)

            except Exception as e:
                print(f"❌ Search exception: {str(e)}")
                return results

        if current_key_index >= len(api_keys):
            print("🚫 ALL API KEYS EXHAUSTED for today.")
            break

    print(f"✅ Search complete. Fetched {len(results)} videos.")
    return results