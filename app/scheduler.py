import logging
from apscheduler.schedulers.background import BackgroundScheduler
from app.core.database import SessionLocal

# --- WORKERS ---
# Note: sync_video_to_lead is now called inside run_youtube (main_worker)
from app.workers.youtube.main_worker import run as run_youtube
from app.workers.campaign.ai_generator import run_ai_generation
from app.workers.campaign.email_worker import run_email_campaigns
# from app.workers.campaign.instagram_worker import instagram_automation

logger = logging.getLogger(__name__)
scheduler = BackgroundScheduler()

# ---------------------------------------------------------
# SCHEDULER SETUP
# ---------------------------------------------------------
def start_scheduler():
    if scheduler.running:
        return

    # 1. YouTube Discovery & Lead Generation (Every 1 hour)
    # This now finds videos AND creates the associated leads in one pass.
    scheduler.add_job(
        run_youtube, 
        "interval", 
        hours=3, 
        id="youtube_discovery",
        max_instances=1,
        replace_existing=True
    )
    
    # 2. AI Generation (Every 5 minutes)
    # Picks up 'queued' leads and generates personalized bodies/subjects.
    scheduler.add_job(
        run_ai_generation, 
        "interval", 
        minutes=5, 
        id="ai_gen",
        max_instances=1
    )
    
    # 3. Outreach Execution (Every 10 minutes)
    # Sends emails for campaigns marked as 'running'.
    scheduler.add_job(
        run_email_campaigns, 
        "interval", 
        minutes=10, 
        id="email_sender",
        max_instances=1
    )
    
    # 4. Instagram Automation (Optional - currently manual or testing)
    # scheduler.add_job(instagram_automation, "interval", minutes=30, id="ig_bot")
    
    scheduler.start()
    logger.info("🚀 Background Scheduler Started: Discovery -> AI -> Outreach pipeline active.")

def shutdown_scheduler():
    if scheduler.running:
        scheduler.shutdown()
        logger.info("🛑 Background Scheduler Shutdown.")