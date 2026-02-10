import sys
import os
import traceback
from datetime import datetime

# Ensure the app module is found
sys.path.append(os.path.abspath("."))

from dotenv import load_dotenv
from sqlalchemy.orm import Session

# Core Imports
from app.core.database import SessionLocal
from app.models.automation_job import AutomationJob

# Worker Components
from app.workers.youtube.youtube_search import search_videos
from app.workers.youtube.channel_fetcher import fetch_channels
from app.workers.youtube.video_fetcher import fetch_videos
from app.workers.youtube.category_fetcher import get_active_categories
from app.workers.youtube.about_scraper import scrape_all_about
from app.workers.youtube.transformers import transform_all
from app.workers.youtube.bulk_writer import bulk_write_all
from app.workers.youtube.stats_writer import write_stats
from app.workers.youtube.lead_builder import build_leads

load_dotenv()

API_KEY = os.getenv("YOUTUBE_API_KEY")

def run():
    db: Session = SessionLocal()
    job = None

    try:
        # ---------------------------------------------------------
        # 1. START JOB LOGGING
        # ---------------------------------------------------------
        job = AutomationJob(
            job_type="youtube_discovery",
            status="running",
            started_at=datetime.utcnow(),
            created_at=datetime.utcnow()
        )
        db.add(job)
        db.commit()
        db.refresh(job)

        print(f"🚀 Job Started: ID {job.id}")

        # ---------------------------------------------------------
        # 2. FETCH ACTIVE CATEGORIES
        # ---------------------------------------------------------
        categories = get_active_categories(db)
        print(f"📂 Found {len(categories)} active categories.")

        for cat in categories:
            try:
                print(f"\n--- Processing: {cat.name} ---")

                # ---------------------------------------------------------
                # A. SEARCH (Find new videos/channels)
                # ---------------------------------------------------------
                # Note: We pass cat.last_fetched_at to only get NEW content
                results = search_videos(API_KEY, cat.youtube_query, cat.last_fetched_at)

                if not results:
                    print(f"⚠️ No new videos found for {cat.name}.")
                    # Update timestamp anyway so we don't query "ancient history" next time
                    cat.last_fetched_at = datetime.utcnow()
                    db.commit()
                    continue

                # Extract IDs
                # We do NOT deduplicate here because we want to UPSERT (update) 
                # existing channels with fresh stats (Sub count, View count).
                channel_ids = list(set([r["channel_id"] for r in results]))
                video_ids = list(set([r["video_id"] for r in results]))

                print(f"🔎 Found {len(video_ids)} videos from {len(channel_ids)} channels.")

                # ---------------------------------------------------------
                # B. FETCH DETAILS (API)
                # ---------------------------------------------------------
                channels_raw = fetch_channels(API_KEY, channel_ids)
                videos_raw = fetch_videos(API_KEY, video_ids)

                if not channels_raw:
                    print("❌ Failed to fetch channel details. Skipping batch.")
                    continue

                # ---------------------------------------------------------
                # C. SCRAPE ABOUT PAGES (The 'Secret Sauce')
                # ---------------------------------------------------------
                print("🕷️ Scraping About pages (this may take a moment)...")
                about_data = scrape_all_about(channel_ids)

                # ---------------------------------------------------------
                # D. TRANSFORM & ENRICH
                # ---------------------------------------------------------
                # This calculates Engagement Rates & formats data for DB
                payload = transform_all(channels_raw, videos_raw, about_data,category_id=cat.id)

                # ---------------------------------------------------------
                # E. BULK WRITE (UPSERT)
                # ---------------------------------------------------------
                # Saves Channels, Videos, Emails, Socials, and Metrics
                bulk_write_all(db, payload)

                # ---------------------------------------------------------
                # F. UPDATE STATS & BUILD LEADS
                # ---------------------------------------------------------
                write_stats(db, payload, cat.name)
                build_leads(db)

                # ---------------------------------------------------------
                # G. UPDATE CATEGORY CURSOR
                # ---------------------------------------------------------
                cat.last_fetched_at = datetime.utcnow()
                db.commit()

                print(f"✅ Completed: {cat.name}")

            except Exception as e:
                # Catch Category-level errors so the whole job doesn't die
                db.rollback()
                print(f"❌ Error processing category '{cat.name}': {str(e)}")
                traceback.print_exc()
                continue

        # ---------------------------------------------------------
        # 3. FINISH JOB LOGGING
        # ---------------------------------------------------------
        job.status = "completed"
        job.finished_at = datetime.utcnow()
        db.commit()
        print("🎉 Worker finished successfully.")

    except Exception as e:
        # ---------------------------------------------------------
        # CRITICAL FAILURE
        # ---------------------------------------------------------
        print(f"🔥 CRITICAL WORKER FAILURE: {str(e)}")
        if job:
            job.status = "failed"
            job.finished_at = datetime.utcnow()
            job.error_message = f"{str(e)}\n{traceback.format_exc()}"
            db.commit()
    
    finally:
        db.close()

if __name__ == "__main__":
    run()