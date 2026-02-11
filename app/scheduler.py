import logging
from apscheduler.schedulers.background import BackgroundScheduler
from app.core.database import SessionLocal
from app.models.youtube_channel import YoutubeChannel

# --- WORKERS ---
from app.workers.lead.lead_sync import sync_channel_to_lead
from app.workers.youtube.main_worker import run as run_youtube
from app.workers.campaign.ai_generator import run_ai_generation
from app.workers.campaign.email_worker import run_email_campaigns

logger = logging.getLogger(__name__)
scheduler = BackgroundScheduler()

# ---------------------------------------------------------
# WRAPPER: Bulk Lead Sync
# ---------------------------------------------------------
def run_lead_sync_batch():
    """
    Creates a DB session and runs sync_channel_to_lead for every channel.
    This bridges the gap between the Scheduler (no args) and the Worker (needs args).
    """
    db = SessionLocal()
    try:
        logger.info("🔄 Scheduler: Starting Bulk Lead Sync...")
        
        # 1. Fetch all channel IDs
        # Optimization: You could filter this to only recently updated channels if needed
        channels = db.query(YoutubeChannel.channel_id).all()
        
        count = 0
        for ch in channels:
            # ch is a Row object, access channel_id
            sync_channel_to_lead(db, ch.channel_id)
            count += 1
            
        logger.info(f"✅ Scheduler: Synced {count} leads successfully.")
        
    except Exception as e:
        logger.error(f"❌ Scheduler Error (Lead Sync): {str(e)}")
    finally:
        db.close()

# ---------------------------------------------------------
# SCHEDULER SETUP
# ---------------------------------------------------------
def start_scheduler():
    if scheduler.running:
        return

    # 1. Discovery (Every 1 hour)
    scheduler.add_job(run_youtube, "interval", hours=1, id="youtube_discovery")
    
    # 2. AI Generation (Every 5 minutes)
    scheduler.add_job(run_ai_generation, "interval", minutes=5, id="ai_gen")
    
    # 3. Email Sending (Every 10 minutes)
    scheduler.add_job(run_email_campaigns, "interval", minutes=10, id="email_sender")
    
    # 4. Instagram (Commented out until file exists/is imported correctly)
    # scheduler.add_job(instagram_automation, "interval", minutes=30, id="ig_bot")
    
    # 5. Lead Sync (The Fix: Call the Wrapper, not the raw function)
    scheduler.add_job(run_lead_sync_batch, "interval", hours=1, id="lead_sync") 
    
    scheduler.start()
    logger.info("🚀 Background Scheduler Started.")