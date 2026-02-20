"""
app/workers/youtube/main_worker.py

Master orchestration worker. Runs the full YouTube discovery pipeline:

  For each active category:
    1. Expand category → N search jobs via search_matrix
    2. Execute each search job (multi-threaded) → raw video/channel IDs
    3. Deduplicate results across all jobs
    4. Fetch full channel + video details from YouTube API
    5. Scrape About pages for emails/socials
    6. Transform + Enrich (emails, lead scoring)
    7. Bulk upsert to PostgreSQL
    8. Create Leads for channels with email/instagram

Scale targets with 10–20 API keys:
  - 10,000+ unique videos per daily run
  - 1,000+ email leads per day
"""

import sys
import os
import time
import traceback
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed
from dotenv import load_dotenv
from sqlalchemy.orm import Session

sys.path.append(os.path.abspath("."))
load_dotenv()

# ── Core ────────────────────────────────────────────────────────────────────
from app.core.database import SessionLocal
from app.models.automation_job import AutomationJob
from app.models.lead import Lead

# ── Worker Components ────────────────────────────────────────────────────────
from app.workers.youtube.key_manager import APIKeyManager
from app.workers.youtube.search_matrix import get_search_jobs
from app.workers.youtube.youtube_search import search_videos
from app.workers.youtube.channel_fetcher import fetch_channels
from app.workers.youtube.video_fetcher import fetch_videos
from app.workers.youtube.category_fetcher import get_active_categories
from app.workers.youtube.about_scraper import scrape_all_about
from app.workers.youtube.transformers import transform_all
from app.workers.youtube.bulk_writer import bulk_write_all
from app.workers.youtube.stats_writer import write_stats


# ══════════════════════════════════════════════════════════════════════════════
# CONFIGURATION
# ══════════════════════════════════════════════════════════════════════════════

# How many search jobs to run in parallel per category
# Keep at 4–6 to avoid hammering the API too fast
SEARCH_JOB_THREADS = 5

# How many about-page scrape threads to use (increased from old default of 6)
ABOUT_SCRAPE_THREADS = 25

# Max raw results per search job before we stop paginating
# 500 = YouTube's hard cap (10 pages × 50 results)
RESULTS_PER_JOB = 250

# Lookback windows
LOOKBACK_FIRST_RUN_DAYS = 7        # If category never ran before
LOOKBACK_NORMAL_HOURS = 26         # Slightly more than 24h to avoid gaps
LOOKBACK_STALE_THRESHOLD_HOURS = 48  # If last run was >48h ago, go back 72h


# ══════════════════════════════════════════════════════════════════════════════
# HELPERS
# ══════════════════════════════════════════════════════════════════════════════

def _get_lookback(cat) -> datetime:
    """
    Returns the publishedAfter datetime for a category based on when it last ran.
    Dynamic windows prevent both data gaps and re-fetching too many old videos.
    """
    now = datetime.utcnow()

    if cat.last_fetched_at is None:
        # First ever run — go back 7 days to seed the database
        lookback = now - timedelta(days=LOOKBACK_FIRST_RUN_DAYS)
        print(f"   📅 First run for '{cat.name}' — lookback: {LOOKBACK_FIRST_RUN_DAYS} days")
        return lookback

    hours_since = (now - cat.last_fetched_at).total_seconds() / 3600

    if hours_since > LOOKBACK_STALE_THRESHOLD_HOURS:
        # Worker was down for a while — fetch an extra buffer
        window_hours = int(hours_since) + 24
        lookback = now - timedelta(hours=window_hours)
        print(f"   📅 Stale run ({hours_since:.0f}h gap) — lookback: {window_hours}h")
    else:
        lookback = now - timedelta(hours=LOOKBACK_NORMAL_HOURS)
        print(f"   📅 Normal run — lookback: {LOOKBACK_NORMAL_HOURS}h")

    return lookback


def _run_search_job(job: dict, key_manager: APIKeyManager, published_after: datetime) -> list[dict]:
    """
    Executes ONE search job and returns raw results.
    Designed to run inside a ThreadPoolExecutor.
    """
    try:
        results = search_videos(
            key_manager=key_manager,
            query=job["query"],
            published_after=published_after,
            target_count=RESULTS_PER_JOB,
            region_code=job["region_code"],
            language=job["language"],
        )
        return results

    except Exception as e:
        print(f"   ❌ Search job failed [{job['query'][:30]} / {job['region_code']}]: {e}")
        return []


def _deduplicate(raw_results: list[dict]) -> tuple[list[str], list[str]]:
    """
    Deduplicates raw results by video_id and channel_id.
    Returns (unique_video_ids, unique_channel_ids).
    """
    seen_vids: set[str] = set()
    seen_chans: set[str] = set()

    for r in raw_results:
        seen_vids.add(r["video_id"])
        seen_chans.add(r["channel_id"])

    return list(seen_vids), list(seen_chans)


# ══════════════════════════════════════════════════════════════════════════════
# CATEGORY PROCESSOR
# ══════════════════════════════════════════════════════════════════════════════

def _process_category(cat, key_manager: APIKeyManager, db: Session) -> dict:
    """
    Runs the full pipeline for ONE category.
    Returns a summary dict for job logging.
    """
    summary = {
        "category": cat.name,
        "jobs_run": 0,
        "raw_results": 0,
        "unique_videos": 0,
        "unique_channels": 0,
        "emails_found": 0,
        "leads_created": 0,
        "errors": [],
    }

    try:
        print(f"\n{'═'*60}")
        print(f"📂 Processing category: {cat.name}  (id={cat.id})")
        print(f"{'═'*60}")

        # ── Step 1: Get search jobs from matrix ────────────────────────
        jobs = get_search_jobs(cat.name)
        if not jobs:
            print(f"   ⚠️  No search matrix for '{cat.name}'. Using fallback DB query.")
            # Fallback: use the raw DB query string as a single job
            jobs = [{
                "query": cat.youtube_query,
                "region_code": "IN",
                "language": "hi",
                "category_name": cat.name,
            }]

        summary["jobs_run"] = len(jobs)

        # ── Step 2: Determine lookback window ──────────────────────────
        published_after = _get_lookback(cat)

        # ── Step 3: Run search jobs in parallel ────────────────────────
        print(f"   🔎 Running {len(jobs)} search jobs with {SEARCH_JOB_THREADS} threads...")
        all_raw: list[dict] = []

        with ThreadPoolExecutor(max_workers=SEARCH_JOB_THREADS) as executor:
            futures = {
                executor.submit(_run_search_job, job, key_manager, published_after): job
                for job in jobs
            }
            for future in as_completed(futures):
                job = futures[future]
                try:
                    batch = future.result()
                    all_raw.extend(batch)
                    if batch:
                        print(
                            f"   ✅  [{job['region_code']}/{job['language']}] "
                            f"'{job['query'][:35]}' → {len(batch)} results"
                        )
                except Exception as e:
                    err = f"Job exception [{job['query'][:30]}]: {e}"
                    print(f"   ❌ {err}")
                    summary["errors"].append(err)

        summary["raw_results"] = len(all_raw)
        print(f"\n   📊 Total raw results: {len(all_raw):,}")

        if not all_raw:
            print(f"   ⚠️  Zero results for '{cat.name}'. Skipping downstream steps.")
            return summary

        # ── Step 4: Deduplicate ────────────────────────────────────────
        video_ids, channel_ids = _deduplicate(all_raw)
        summary["unique_videos"] = len(video_ids)
        summary["unique_channels"] = len(channel_ids)

        print(
            f"   🗂️  After dedup: {len(video_ids):,} unique videos "
            f"from {len(channel_ids):,} unique channels"
        )

        # ── Step 5: Fetch Full Details (YouTube API) ───────────────────
        key_for_fetch = key_manager.get_key()
        if not key_for_fetch:
            print(f"   💀 No API keys left. Cannot fetch details for '{cat.name}'.")
            return summary

        print(f"   📡 Fetching channel details ({len(channel_ids)} channels)...")
        channels_raw = fetch_channels(key_for_fetch, channel_ids)

        print(f"   📡 Fetching video details ({len(video_ids)} videos)...")
        videos_raw = fetch_videos(key_for_fetch, video_ids)

        if not channels_raw:
            print(f"   ❌ Channel fetch returned empty. Skipping '{cat.name}'.")
            summary["errors"].append("channels_raw empty after fetch")
            return summary

        print(
            f"   ✅  Fetched: {len(channels_raw)} channels, {len(videos_raw)} videos"
        )

        # ── Step 6: Scrape About Pages ─────────────────────────────────
        print(f"   🕷️  Scraping About pages ({len(channel_ids)} channels, {ABOUT_SCRAPE_THREADS} threads)...")
        # Temporarily patch max_workers in about_scraper via monkey-patch approach
        # OR ensure about_scraper.scrape_all_about uses the constant below
        about_data = scrape_all_about(channel_ids)

        # ── Step 7: Transform & Enrich ─────────────────────────────────
        print(f"   🔄 Transforming data...")
        payload = transform_all(
            channels_raw,
            videos_raw,
            about_data,
            category_id=cat.id,
        )

        emails_count = len(payload.get("emails", []))
        summary["emails_found"] = emails_count
        print(
            f"   📧 Emails extracted: {emails_count} "
            f"| Channels with email: {sum(1 for c in payload['channels'] if c.primary_email)}"
        )

        # ── Step 8: Bulk Write to DB ────────────────────────────────────
        print(f"   💾 Writing to database...")
        bulk_write_all(db, payload)
        write_stats(db, payload, cat.name)

        # ── Step 9: Lead Generation ─────────────────────────────────────
        leads_created = 0
        print(f"   🎯 Evaluating {len(payload['videos'])} videos for leads...")

        for video_obj in payload["videos"]:
            # Skip if lead already exists for this video
            exists = db.query(Lead).filter(Lead.video_id == video_obj.video_id).first()
            if exists:
                continue

            channel_id = video_obj.channel_id
            channel_data = next(
                (c for c in payload["channels"] if c.channel_id == channel_id),
                None,
            )

            if not channel_data:
                continue

            email = channel_data.primary_email
            ig_url = channel_data.primary_instagram

            # Only create a lead if we have at least one contact point
            if not email and not ig_url:
                continue

            lead = Lead(
                channel_id=channel_id,
                video_id=video_obj.video_id,
                primary_email=email,
                instagram_username=ig_url,
                status="new",
                notes=(
                    f"Channel: {channel_data.name}\n"
                    f"Subs: {channel_data.subscriber_count}\n"
                    f"Category: {cat.name}\n"
                    f"Video: {video_obj.title}\n"
                    f"Published: {video_obj.published_at}"
                ),
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
            )
            db.add(lead)
            leads_created += 1

        db.commit()
        summary["leads_created"] = leads_created
        print(f"   ✅  Leads created: {leads_created}")

        # ── Step 10: Update category last_fetched_at ────────────────────
        cat.last_fetched_at = datetime.utcnow()
        db.commit()

    except Exception as e:
        tb = traceback.format_exc()
        print(f"   💥 Category '{cat.name}' crashed:\n{tb}")
        summary["errors"].append(str(e))

    return summary


# ══════════════════════════════════════════════════════════════════════════════
# MAIN ENTRY POINT
# ══════════════════════════════════════════════════════════════════════════════

def run():
    """
    Main worker entry point. Called by the scheduler / CLI.

    Usage:
        python -m app.workers.youtube.main_worker
        # or via APScheduler / Celery every 2–4 hours
    """
    db: Session = SessionLocal()
    job = None
    start_time = datetime.utcnow()

    try:
        # ── 1. Initialize shared API key pool ──────────────────────────
        print("\n" + "═" * 70)
        print(f"🚀 YouTube Discovery Worker — {start_time.strftime('%Y-%m-%d %H:%M UTC')}")
        print("═" * 70)

        key_manager = APIKeyManager()
        key_status = key_manager.status()
        print(f"🔑 Key Pool: {key_status['active']} active keys ({key_status['total_keys']} total)")

        # ── 2. Log job start ───────────────────────────────────────────
        job = AutomationJob(
            job_type="youtube_discovery",
            status="running",
            started_at=start_time,
            created_at=start_time,
        )
        db.add(job)
        db.commit()
        db.refresh(job)
        print(f"📝 Job ID: {job.id}")

        # ── 3. Load active categories ──────────────────────────────────
        categories = get_active_categories(db)
        print(f"📂 Active categories: {len(categories)}")
        for cat in categories:
            print(f"   • [{cat.id}] {cat.name}")

        # ── 4. Process each category (sequential — each uses threaded jobs internally) ──
        # We process categories sequentially to keep DB writes clean and
        # avoid key_manager race conditions at the category level.
        # The parallelism is inside each category (search job threads).

        all_summaries = []
        total_videos = 0
        total_leads = 0

        for cat in categories:
            summary = _process_category(cat, key_manager, db)
            all_summaries.append(summary)
            total_videos += summary["unique_videos"]
            total_leads += summary["leads_created"]

            # Check if we still have keys left
            remaining = key_manager.status()["active"]
            if remaining == 0:
                print("\n💀 All API keys exhausted. Stopping worker early.")
                break

            # Brief pause between categories to let rate limits breathe
            time.sleep(2)

        # ── 5. Final summary ───────────────────────────────────────────
        elapsed = (datetime.utcnow() - start_time).total_seconds()
        print("\n" + "═" * 70)
        print(f"🏁 Worker Complete — {elapsed:.0f}s elapsed")
        print("═" * 70)
        print(f"   📺 Total unique videos discovered : {total_videos:,}")
        print(f"   📧 Total leads created            : {total_leads:,}")
        print(f"   🔑 Keys remaining                 : {key_manager.status()['active']}/{key_manager.status()['total_keys']}")
        print()

        for s in all_summaries:
            status_icon = "✅" if not s["errors"] else "⚠️ "
            print(
                f"   {status_icon} {s['category']:<30} "
                f"jobs={s['jobs_run']:>4}  "
                f"raw={s['raw_results']:>6,}  "
                f"videos={s['unique_videos']:>5,}  "
                f"emails={s['emails_found']:>4}  "
                f"leads={s['leads_created']:>4}"
            )

        # ── 6. Mark job as complete ────────────────────────────────────
        job.status = "completed"
        job.completed_at = datetime.utcnow()
        job.result_summary = str({
            "total_videos": total_videos,
            "total_leads": total_leads,
            "categories": len(all_summaries),
        })
        db.commit()

    except Exception as e:
        tb = traceback.format_exc()
        print(f"\n💥 WORKER CRASHED:\n{tb}")

        if job:
            job.status = "failed"
            job.error_message = str(e)
            job.completed_at = datetime.utcnow()
            db.commit()

    finally:
        db.close()


# ── CLI entry ──────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    run()