import requests
from concurrent.futures import ThreadPoolExecutor

BASE = "https://www.googleapis.com/youtube/v3/channels"

def _fetch(api_key, chunk):

    ids = ",".join(chunk)

    params = {
        "part": "snippet,statistics",
        "id": ids,
        "key": api_key
    }

    r = requests.get(BASE, params=params, timeout=20)
    r.raise_for_status()

    return r.json().get("items", [])

def fetch_channels(api_key, channel_ids):

    chunks = [channel_ids[i:i+50] for i in range(0, len(channel_ids), 50)]

    data = []

    with ThreadPoolExecutor(max_workers=5) as pool:
        for res in pool.map(lambda c: _fetch(api_key, c), chunks):
            data.extend(res)

    return data
