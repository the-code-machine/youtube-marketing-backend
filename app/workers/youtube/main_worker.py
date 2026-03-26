"""
app/workers/youtube/main_worker.py

HYBRID ARCHITECTURE — Proven working after RSS search confirmed dead
═════════════════════════════════════════════════════════════════════

DISCOVERY (new channels):   YouTube API search  → controlled quota (~50 results/job)
MONITORING (known channels): Channel RSS        → 0 units, works perfectly
ENRICHMENT:                  YouTube API        → new channels only
EMAILS:                      About scraper      → 0 units

WHY HYBRID:
  YouTube killed RSS search feeds (returns 400).
  Channel RSS (per channel_id) still works perfectly — confirmed 79K videos.
  API search is still needed to discover BRAND NEW channels we've never seen.
  But we use it sparingly: 1 page (50 results) per query, not 10 pages.

QUOTA MATH (3 keys = 30,000 units/day):
  API search for new channels:  10 queries × 100 units = 1,000 units/run
  API enrichment (new only):    ~200 units/run
  Total per run:                ~1,200 units
  3 keys = 30,000 ÷ 1,200 = 25 runs/day ✅ (schedule every 1-2 hours)

ALL FIXES:
  ✅ Channel RSS monitoring (known channels — confirmed working)
  ✅ API search for NEW channel discovery (low quota, 1 page only)
  ✅ DB filter before API enrichment (new channels/videos only)
  ✅ Bulk lead check (1 query not N queries)
  ✅ Bulk lead insert
  ✅ Leads from KNOWN channels (uses DB contact info)
  ✅ Leads from NEW channels (uses payload contact info)
  ✅ About scraper batched (300 at a time, 10 threads, 3GB safe)
  ✅ Retry on empty channel fetch
  ✅ DB rollback on crash
"""

import sys
import os
import time
import traceback
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed
from dotenv import load_dotenv
from sqlalchemy.orm import Session
from sqlalchemy import text

sys.path.append(os.path.abspath("."))
load_dotenv()

# ── Core ──────────────────────────────────────────────────────────────────────
from app.core.database import SessionLocal
from app.models.automation_job import AutomationJob
from app.models.lead import Lead

# ── Worker Components ─────────────────────────────────────────────────────────
from app.workers.youtube.key_manager import APIKeyManager
from app.workers.youtube.rss_worker import monitor_known_channels
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

# API search for new channel discovery
# 1 page = 50 results = 100 units per job
# Keep low to preserve quota for enrichment
API_SEARCH_TARGET      = 50    # 1 page only per job
API_SEARCH_THREADS     = 5     # parallel search jobs

# Channel RSS monitoring
RSS_MONITOR_THREADS    = 20    # threads for known channel RSS checks
KNOWN_CHANNEL_LIMIT    = 3000  # max known channels to re-check per run

# About scraper (3GB RAM safe)
ABOUT_SCRAPE_THREADS   = 10
ABOUT_SCRAPE_BATCH     = 300

# Lookback windows
LOOKBACK_FIRST_RUN_DAYS      = 3
LOOKBACK_NORMAL_HOURS        = 26
LOOKBACK_STALE_THRESHOLD_HRS = 48


# ══════════════════════════════════════════════════════════════════════════════
# SEARCH QUERIES PER CATEGORY
# Short list — 1 page each = minimal quota for new channel discovery
# ══════════════════════════════════════════════════════════════════════════════

CATEGORY_SEARCH_QUERIES = {
    "Music Creators": [
        "official music video 2026",
        "new song 2026",
        "indie artist music video",
        "hip hop music video 2026",
        "afrobeats music video 2026",
    ],
    "Podcast Creators": [
        "podcast episode 2026",
        "business podcast new episode",
        "entrepreneur interview podcast",
    ],
    "Finance & Investing": [
        "stock market investing 2026",
        "personal finance tips new",
        "crypto trading tutorial 2026",
        "investing for beginners",
    ],
    "Education & Tech": [
        "coding tutorial beginner 2026",
        "python tutorial beginners",
        "web development tutorial new",
        "ai tools tutorial 2026",
    ],
    "Gaming Creators": [
        "gaming channel new video 2026",
        "lets play gameplay 2026",
        "game review new release",
        "minecraft gameplay 2026",
    ],
    "Fitness & Health": [
        "workout tutorial beginner 2026",
        "home workout no equipment",
        "yoga for beginners new",
    ],
    "Food & Cooking": [
        "cooking tutorial easy recipe",
        "food vlog new video",
        "recipe video beginner",
    ],
    "Comedy & Entertainment": [
        "comedy skit funny video 2026",
        "stand up comedy new",
        "sketch comedy new video",
    ],
    "Business & Entrepreneurship": [
        "how to start a business 2026",
        "entrepreneur vlog new",
        "side hustle ideas new",
        "online business tutorial",
    ],
    "Lifestyle & Travel Vlogs": [
        "travel vlog new video 2026",
        "day in my life vlog",
        "digital nomad vlog 2026",
    ],
}


# ══════════════════════════════════════════════════════════════════════════════
# HELPERS
# ══════════════════════════════════════════════════════════════════════════════

def _get_lookback(cat) -> datetime:
    now = datetime.utcnow()
    if cat.last_fetched_at is None:
        print(f"   📅 First run — lookback {LOOKBACK_FIRST_RUN_DAYS} days")
        return now - timedelta(days=LOOKBACK_FIRST_RUN_DAYS)
    hours_since = (now - cat.last_fetched_at).total_seconds() / 3600
    if hours_since > LOOKBACK_STALE_THRESHOLD_HRS:
        window = int(hours_since) + 24
        print(f"   📅 Stale ({hours_since:.0f}h gap) — lookback {window}h")
        return now - timedelta(hours=window)
    print(f"   📅 Normal — lookback {LOOKBACK_NORMAL_HOURS}h")
    return now - timedelta(hours=LOOKBACK_NORMAL_HOURS)


def _get_known_channel_ids(db: Session, category_id: int) -> list[str]:
    """Most recently active channels in DB for this category."""
    result = db.execute(text("""
        SELECT channel_id FROM youtube_channels
        WHERE category_id = :cat_id AND is_active = true
        ORDER BY last_video_published_at DESC NULLS LAST
        LIMIT :limit
    """), {"cat_id": category_id, "limit": KNOWN_CHANNEL_LIMIT})
    return [row[0] for row in result.fetchall()]


def _filter_new_channels(db: Session, channel_ids: list[str]) -> list[str]:
    if not channel_ids:
        return []
    result = db.execute(text(
        "SELECT channel_id FROM youtube_channels WHERE channel_id = ANY(:ids)"
    ), {"ids": channel_ids})
    existing = {row[0] for row in result.fetchall()}
    new_ids = [c for c in channel_ids if c not in existing]
    print(f"   🔍 Channels: {len(channel_ids):,} found → {len(new_ids):,} new, {len(existing):,} in DB")
    return new_ids


def _filter_new_videos(db: Session, video_ids: list[str]) -> list[str]:
    if not video_ids:
        return []
    result = db.execute(text(
        "SELECT video_id FROM youtube_videos WHERE video_id = ANY(:ids)"
    ), {"ids": video_ids})
    existing = {row[0] for row in result.fetchall()}
    new_ids = [v for v in video_ids if v not in existing]
    print(f"   🎬 Videos: {len(video_ids):,} found → {len(new_ids):,} new, {len(existing):,} in DB")
    return new_ids


def _get_existing_lead_video_ids(db: Session, video_ids: list[str]) -> set[str]:
    """Bulk check — 1 query instead of N queries inside loop."""
    if not video_ids:
        return set()
    result = db.execute(text(
        "SELECT video_id FROM leads WHERE video_id = ANY(:ids)"
    ), {"ids": video_ids})
    return {row[0] for row in result.fetchall()}


def _get_db_channel_contacts(db: Session, channel_ids: list[str]) -> dict:
    """
    Fetch stored contact info for known channels from DB.
    Used to generate leads from RSS-discovered videos of known channels.
    """
    if not channel_ids:
        return {}
    result = db.execute(text("""
        SELECT channel_id, primary_email, primary_instagram, name, subscriber_count
        FROM youtube_channels
        WHERE channel_id = ANY(:ids)
          AND (primary_email IS NOT NULL OR primary_instagram IS NOT NULL)
    """), {"ids": channel_ids})
    contacts = {}
    for row in result.fetchall():
        contacts[row[0]] = {
            "email":     row[1],
            "instagram": row[2],
            "name":      row[3],
            "subs":      row[4],
        }
    return contacts


def _api_search_new_channels(
    key_manager: APIKeyManager,
    category_name: str,
    published_after: datetime,
) -> list[dict]:
    """
    Uses YouTube API search to discover BRAND NEW channels.
    Only 1 page (50 results) per query to preserve quota.
    Returns list of {video_id, channel_id, published_at}.
    """
    queries = CATEGORY_SEARCH_QUERIES.get(category_name, [])
    if not queries:
        return []

    api_key = key_manager.get_key()
    if not api_key:
        print(f"   ⚠️  No API key for search — skipping new channel discovery")
        return []

    all_results = []
    seen = set()

    print(f"   🔎 API search: {len(queries)} queries for new channels...")

    def _run_query(query):
        try:
            results = search_videos(
                key_manager=key_manager,
                query=query,
                published_after=published_after,
                target_count=API_SEARCH_TARGET,
                region_code="US",
                language="en",
            )
            return results
        except Exception as e:
            print(f"   ❌ Search failed [{query[:30]}]: {e}")
            return []

    with ThreadPoolExecutor(max_workers=API_SEARCH_THREADS) as executor:
        futures = {executor.submit(_run_query, q): q for q in queries}
        for future in as_completed(futures):
            try:
                for item in future.result():
                    if item["video_id"] not in seen:
                        seen.add(item["video_id"])
                        all_results.append(item)
            except Exception:
                pass

    print(f"   🔎 API search found: {len(all_results):,} results")
    return all_results


def _scrape_about_batched(channel_ids: list[str]) -> dict:
    """Batched about scraping — memory safe for 3GB server."""
    if not channel_ids:
        return {}
    all_about = {}
    batches = [channel_ids[i:i+ABOUT_SCRAPE_BATCH] for i in range(0, len(channel_ids), ABOUT_SCRAPE_BATCH)]
    print(f"   🕷️  About scrape: {len(channel_ids):,} channels in {len(batches)} batch(es)...")
    for i, batch in enumerate(batches):
        print(f"      Batch {i+1}/{len(batches)} ({len(batch)} channels)...")
        all_about.update(scrape_all_about(batch))
        time.sleep(0.5)
    emails_found = sum(1 for v in all_about.values() if v.get("email"))
    print(f"   📧 About scrape: {emails_found} emails found")
    return all_about


# ══════════════════════════════════════════════════════════════════════════════
# CATEGORY PROCESSOR
# ══════════════════════════════════════════════════════════════════════════════

def _process_category(cat, key_manager: APIKeyManager, db: Session) -> dict:
    summary = {
        "category":             cat.name,
        "rss_videos":           0,
        "api_search_videos":    0,
        "new_channels":         0,
        "new_videos":           0,
        "emails_found":         0,
        "leads_created":        0,
        "api_units_used":       0,
        "errors":               [],
    }

    try:
        print(f"\n{'═'*60}")
        print(f"📂 {cat.name}  (id={cat.id})")
        print(f"{'═'*60}")

        published_after = _get_lookback(cat)
        all_results = []
        seen_vids = set()

        # ── Step 1: Channel RSS (known channels — zero quota) ─────────
        known_channel_ids = _get_known_channel_ids(db, cat.id)
        if known_channel_ids:
            rss_results = monitor_known_channels(
                channel_ids=known_channel_ids,
                published_after=published_after,
                threads=RSS_MONITOR_THREADS,
            )
            summary["rss_videos"] = len(rss_results)
            for r in rss_results:
                if r["video_id"] not in seen_vids:
                    seen_vids.add(r["video_id"])
                    all_results.append(r)
        else:
            print(f"   📡 No known channels yet")

        # ── Step 2: API Search (new channel discovery) ────────────────
        api_results = _api_search_new_channels(key_manager, cat.name, published_after)
        summary["api_search_videos"] = len(api_results)
        for r in api_results:
            if r["video_id"] not in seen_vids:
                seen_vids.add(r["video_id"])
                all_results.append(r)

        print(f"   📊 Combined: {len(all_results):,} unique results "
              f"(rss={summary['rss_videos']:,} + api={summary['api_search_videos']:,})")

        if not all_results:
            print(f"   ⚠️  No results for '{cat.name}'")
            return summary

        all_video_ids   = list({r["video_id"]   for r in all_results})
        all_channel_ids = list({r["channel_id"] for r in all_results})

        # ── Step 3: Filter NEW only ────────────────────────────────────
        new_video_ids   = _filter_new_videos(db, all_video_ids)
        new_channel_ids = _filter_new_channels(db, all_channel_ids)
        summary["new_channels"] = len(new_channel_ids)
        summary["new_videos"]   = len(new_video_ids)

        # ── Step 4: Enrich NEW channels via API ───────────────────────
        channels_raw = []
        videos_raw   = []

        if new_channel_ids or new_video_ids:
            api_key = key_manager.get_key()
            if api_key:
                if new_channel_ids:
                    print(f"   📡 Enriching {len(new_channel_ids):,} new channels...")
                    channels_raw = fetch_channels(api_key, new_channel_ids)
                    # Retry once on empty
                    if not channels_raw and new_channel_ids:
                        print(f"   🔄 Retrying channel fetch...")
                        time.sleep(3)
                        channels_raw = fetch_channels(api_key, new_channel_ids)
                    summary["api_units_used"] += max(1, len(new_channel_ids) // 50)

                if new_video_ids:
                    print(f"   📡 Enriching {len(new_video_ids):,} new videos...")
                    videos_raw = fetch_videos(api_key, new_video_ids)
                    summary["api_units_used"] += max(1, len(new_video_ids) // 50)

                print(f"   💰 API units this category: ~{summary['api_units_used']}")
            else:
                print(f"   ⚠️  No API key — skipping enrichment")

        # ── Step 5: About Scrape (new channels only, batched) ─────────
        about_data = _scrape_about_batched(new_channel_ids) if new_channel_ids else {}

        # ── Step 6: Transform + Write (new channels/videos only) ──────
        payload = {"channels": [], "videos": [], "emails": [], "socials": [], "metrics": [], "lead_context": {}}

        if channels_raw:
            print(f"   🔄 Transforming {len(channels_raw)} channels...")
            payload = transform_all(channels_raw, videos_raw, about_data, category_id=cat.id)
            summary["emails_found"] = len(payload.get("emails", []))
            print(f"   📧 New channel emails: {summary['emails_found']}")
            print(f"   💾 Writing new data to DB...")
            bulk_write_all(db, payload)
            write_stats(db, payload, cat.name)
        else:
            print(f"   ℹ️  No new channels to enrich/write this run")

        # ── Step 7: Lead Generation (BOTH new + known channels) ───────

        # Collect all video_ids we're evaluating for leads
        # = new videos from payload + all RSS-discovered videos
        candidate_videos = []

        # A: New channel videos (just enriched)
        for video_obj in payload["videos"]:
            channel_data = next(
                (c for c in payload["channels"] if c.channel_id == video_obj.channel_id), None
            )
            if channel_data and (channel_data.primary_email or channel_data.primary_instagram):
                candidate_videos.append({
                    "video_id":   video_obj.video_id,
                    "channel_id": video_obj.channel_id,
                    "title":      video_obj.title,
                    "email":      channel_data.primary_email,
                    "instagram":  channel_data.primary_instagram,
                    "name":       channel_data.name,
                    "subs":       channel_data.subscriber_count,
                })

        # B: Known channel videos (from RSS — use DB contact info)
        known_channel_ids_in_results = list({r["channel_id"] for r in all_results})
        db_contacts = _get_db_channel_contacts(db, known_channel_ids_in_results)

        for r in all_results:
            contact = db_contacts.get(r["channel_id"])
            if not contact:
                continue
            candidate_videos.append({
                "video_id":   r["video_id"],
                "channel_id": r["channel_id"],
                "title":      r.get("title", ""),
                "email":      contact["email"],
                "instagram":  contact["instagram"],
                "name":       contact["name"],
                "subs":       contact["subs"],
            })

        # Deduplicate candidate_videos by video_id
        seen_candidate = set()
        unique_candidates = []
        for cv in candidate_videos:
            if cv["video_id"] not in seen_candidate:
                seen_candidate.add(cv["video_id"])
                unique_candidates.append(cv)

        # Bulk check which video_ids already have leads
        all_candidate_ids = [cv["video_id"] for cv in unique_candidates]
        existing_lead_vids = _get_existing_lead_video_ids(db, all_candidate_ids)

        print(f"   🎯 Lead candidates: {len(unique_candidates):,} | already have leads: {len(existing_lead_vids):,}")

        # Build new leads
        new_leads = []
        for cv in unique_candidates:
            if cv["video_id"] in existing_lead_vids:
                continue
            new_leads.append(Lead(
                channel_id=cv["channel_id"],
                video_id=cv["video_id"],
                primary_email=cv["email"],
                instagram_username=cv["instagram"],
                status="new",
                notes=(
                    f"Channel: {cv['name']}\n"
                    f"Subs: {cv['subs']}\n"
                    f"Category: {cat.name}\n"
                    f"Video: {cv['title']}"
                ),
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
            ))

        if new_leads:
            db.bulk_save_objects(new_leads)

        db.commit()
        summary["leads_created"] = len(new_leads)
        print(f"   ✅  Leads created: {len(new_leads):,}")

        # ── Step 8: Update last_fetched_at ─────────────────────────────
        cat.last_fetched_at = datetime.utcnow()
        db.commit()

    except Exception as e:
        print(f"   💥 '{cat.name}' crashed:\n{traceback.format_exc()}")
        summary["errors"].append(str(e))
        try:
            db.rollback()
        except Exception:
            pass

    return summary


# ══════════════════════════════════════════════════════════════════════════════
# MAIN ENTRY POINT
# ══════════════════════════════════════════════════════════════════════════════

def run():
    db: Session = SessionLocal()
    job = None
    start_time = datetime.utcnow()

    try:
        print("\n" + "═" * 70)
        print(f"🚀 YouTube Worker (Hybrid RSS+API) — {start_time.strftime('%Y-%m-%d %H:%M UTC')}")
        print("═" * 70)

        key_manager = APIKeyManager()
        ks = key_manager.status()
        print(f"🔑 Keys: {ks['active']} active / {ks['total_keys']} total")

        job = AutomationJob(
            job_type="youtube_discovery_hybrid",
            status="running",
            started_at=start_time,
            created_at=start_time,
        )
        db.add(job)
        db.commit()
        db.refresh(job)
        print(f"📝 Job ID: {job.id}")

        categories = get_active_categories(db)
        print(f"📂 Active categories: {len(categories)}")
        for cat in categories:
            print(f"   • [{cat.id}] {cat.name}")

        all_summaries = []
        total_videos  = 0
        total_leads   = 0
        total_units   = 0

        for cat in categories:
            summary = _process_category(cat, key_manager, db)
            all_summaries.append(summary)
            total_videos += summary["new_videos"]
            total_leads  += summary["leads_created"]
            total_units  += summary["api_units_used"]
            time.sleep(1)

        elapsed = (datetime.utcnow() - start_time).total_seconds()
        print("\n" + "═" * 70)
        print(f"🏁 Complete — {elapsed:.0f}s | ~{total_units} API units used")
        print("═" * 70)
        print(f"   📺 New videos    : {total_videos:,}")
        print(f"   📧 Leads created : {total_leads:,}")
        print(f"   🔑 Keys remaining: {key_manager.status()['active']}/{key_manager.status()['total_keys']}")
        print()

        for s in all_summaries:
            icon = "✅" if not s["errors"] else "⚠️ "
            print(
                f"   {icon} {s['category']:<35} "
                f"rss={s['rss_videos']:>5}  "
                f"api={s['api_search_videos']:>4}  "
                f"new={s['new_videos']:>5}  "
                f"leads={s['leads_created']:>4}"
            )

        job.status = "completed"
        job.completed_at = datetime.utcnow()
        job.result_summary = str({
            "videos": total_videos,
            "leads":  total_leads,
            "units":  total_units,
        })
        db.commit()

    except Exception as e:
        print(f"\n💥 WORKER CRASHED:\n{traceback.format_exc()}")
        if job:
            try:
                job.status = "failed"
                job.error_message = str(e)
                job.completed_at = datetime.utcnow()
                db.commit()
            except Exception:
                pass
    finally:
        db.close()


if __name__ == "__main__":
    run()