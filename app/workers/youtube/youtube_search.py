from time import timezone
import requests

BASE = "https://www.googleapis.com/youtube/v3/search"

def search_videos(api_key, query, published_after=None):

    params = {
        "part": "snippet",
        "type": "video",
        "q": query,
        "order": "date",
        "maxResults": 50,
        "key": api_key
    }

    if published_after:
        # must be RFC3339
        published_after_new = published_after.replace(tzinfo=timezone.utc).isoformat().replace("+00:00", "Z")
        params["publishedAfter"] = published_after_new

    try:
        resp = requests.get(BASE, params=params, timeout=30)

        if resp.status_code != 200:
            print("❌ YouTube search failed:", resp.text)
            return []

        data = resp.json()

        results = []

        for item in data.get("items", []):

            vid = item.get("id", {}).get("videoId")
            cid = item.get("snippet", {}).get("channelId")

            if not vid or not cid:
                continue

            results.append({
                "video_id": vid,
                "channel_id": cid,
                "published_at": item["snippet"]["publishedAt"]
            })

        return results

    except Exception as e:
        print("❌ Search exception:", str(e))
        return []
