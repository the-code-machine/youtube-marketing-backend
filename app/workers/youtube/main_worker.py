import sys
import os
import traceback
from datetime import datetime, timedelta
from dotenv import load_dotenv
from sqlalchemy.orm import Session

# Core Imports
from app.core.database import SessionLocal
from app.models.automation_job import AutomationJob
from app.models.lead import Lead

# Worker Components
from app.workers.youtube.youtube_search import search_videos
from app.workers.youtube.channel_fetcher import fetch_channels
from app.workers.youtube.video_fetcher import fetch_videos
from app.workers.youtube.category_fetcher import get_active_categories
from app.workers.youtube.about_scraper import scrape_all_about
from app.workers.youtube.transformers import transform_all
from app.workers.youtube.bulk_writer import bulk_write_all
from app.workers.youtube.stats_writer import write_stats

# Ensure the app module is found
sys.path.append(os.path.abspath("."))

load_dotenv()

API_KEY = os.getenv("YOUTUBE_API_KEY")
BACKUP_KEY = os.getenv("EMERGENCY_BACKUP_KEY")
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

                # A. SEARCH (Find new videos/channels)
                # We pass cat.last_fetched_at to only get content since the last run
                
        
        
                if cat.last_fetched_at:
                    lookback = datetime.utcnow() - timedelta(hours=48)
                results, working_key = search_videos(API_KEY, BACKUP_KEY, cat.youtube_query, published_after=lookback, target_count=250)

                # Extract IDs
                channel_ids = list(set([r["channel_id"] for r in results]))
                video_ids = list(set([r["video_id"] for r in results]))

                print(f"🔎 Found {len(video_ids)} videos from {len(channel_ids)} channels.")

                # B. FETCH DETAILS (YouTube API)
                channels_raw = fetch_channels(BACKUP_KEY, channel_ids)
                videos_raw = fetch_videos(BACKUP_KEY, video_ids)

                if not channels_raw:
                    print("❌ Failed to fetch channel details. Skipping batch.")
                    continue

                # C. SCRAPE ABOUT PAGES
                print("🕷️ Scraping About pages (this may take a moment)...")
                about_data = scrape_all_about(channel_ids)

                # D. TRANSFORM & ENRICH
                # This prepares the data for bulk insertion and identifies social links
                payload = transform_all(channels_raw, videos_raw, about_data, category_id=cat.id)

                # E. BULK WRITE (UPSERT)
                # Saves Channels, Videos, Emails, Socials, and Metrics
                bulk_write_all(db, payload)

                # F. UPDATE DAILY/CATEGORY STATS
                write_stats(db, payload, cat.name)
                
                # ---------------------------------------------------------
                # G. INTEGRATED LEAD GENERATION (Video-Based)
                # ---------------------------------------------------------
                print(f"🎯 Evaluating leads for {len(payload['videos'])} new videos...")

                for video_obj in payload["videos"]:
                    # 1. Check if lead already exists for this specific VIDEO_ID
                    exists = db.query(Lead).filter(Lead.video_id == video_obj.video_id).first()
                    if exists:
                        continue

                    # 2. Match video to channel data to extract contact info
                    channel_id = video_obj.channel_id
                    channel_data = next((c for c in payload["channels"] if c.channel_id == channel_id), None)

                    if channel_data:
                        email = channel_data.primary_email
                        ig_url = channel_data.primary_instagram
        
                        # 3. GATEKEEPER: Only create lead if we have at least one contact method
                        if email or ig_url:
                            # Extract clean username from IG URL
                            ig_username = None
                            if ig_url:
                                ig_username = ig_url.rstrip('/').split('/')[-1]

                            new_lead = Lead(
                                channel_id=channel_id,
                                video_id=video_obj.video_id,
                                primary_email=email,
                                instagram_username=ig_username,
                                status="new",
                                notes=f"Video Title: {video_obj.title}\n\nDescription: {video_obj.description[:500]}",
                                created_at=datetime.utcnow(),
                                updated_at=datetime.utcnow()
                            )
                            db.add(new_lead)
                            print(f"✅ Lead Created: {channel_data.name} (Video: {video_obj.video_id})")

                # H. UPDATE CATEGORY CURSOR (Save progress)
                cat.last_fetched_at = datetime.utcnow()
                db.commit()

                print(f"✅ Completed: {cat.name}")

            except Exception as e:
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