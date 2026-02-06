import sys, os, json, csv
from datetime import datetime

from app.workers.youtube.bulk_writer import bulk_write_all
from app.workers.youtube.lead_builder import build_leads
from app.workers.youtube.stats_writer import write_stats

sys.path.append(os.path.abspath("."))

from dotenv import load_dotenv
from app.workers.youtube.youtube_search import search_videos
from app.workers.youtube.channel_fetcher import fetch_channels
from app.workers.youtube.video_fetcher import fetch_videos
from app.workers.youtube.transformers import transform_all
from app.workers.youtube.category_fetcher import get_active_categories
from app.core.database import SessionLocal
from app.workers.youtube.about_scraper import scrape_about, scrape_all_about

load_dotenv()

API_KEY = os.getenv("YOUTUBE_API_KEY")

OUTPUT_DIR = "output"

os.makedirs(OUTPUT_DIR, exist_ok=True)


def run():

    db = SessionLocal()
    categories = get_active_categories(db)

    for cat in categories:

        print("Running:", cat.name)

        results = search_videos(API_KEY, cat.youtube_query, cat.last_fetched_at)

        if not results:
            continue

        channel_ids = list(set([r["channel_id"] for r in results]))
        video_ids = list(set([r["video_id"] for r in results]))

        channels_raw = fetch_channels(API_KEY, channel_ids)
        videos_raw = fetch_videos(API_KEY, video_ids)

        print("Channels:", len(channels_raw))
        print("Videos:", len(videos_raw))

        # Parallel about scraping
        about_data = scrape_all_about(channel_ids)

        payload = transform_all(channels_raw, videos_raw, about_data)

        # bulk insert
        bulk_write_all(db, payload)

        write_stats(db, payload,cat.name)
        build_leads(db)

        # update category cursor
        cat.last_fetched_at = datetime.utcnow()
        db.commit()

        print("Completed:", cat.name)

    db.close()

if __name__ == "__main__":
    run()
