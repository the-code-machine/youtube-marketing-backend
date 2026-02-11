from apscheduler.schedulers.background import BackgroundScheduler
from app.workers.lead.lead_sync import sync_channel_to_lead as lead_sync
from app.workers.youtube.main_worker import run as run_youtube
from app.workers.campaign.ai_generator import run_ai_generation
from app.workers.campaign.email_worker import run_email_campaigns
from app.workers.campaign.instagram_worker import instagram_automation

scheduler = BackgroundScheduler()

def start_scheduler():
    # 1. Discovery (Every 4 hours)
    scheduler.add_job(run_youtube, "interval", hours=1, id="youtube_discovery")
    
    # 2. AI Generation (Every 5 minutes)
    # Checks for new leads added to campaigns and drafts messages
    scheduler.add_job(run_ai_generation, "interval", minutes=5, id="ai_gen")
    
    # 3. Email Sending (Every 10 minutes)
    # Sends batches of "ready" emails
    scheduler.add_job(run_email_campaigns, "interval", minutes=10, id="email_sender")
    
    # 4. Instagram Automation (Every 30 minutes)
    # Runs slower to be safe
    scheduler.add_job(instagram_automation, "interval", minutes=30, id="ig_bot")
    
    scheduler.add_job(lead_sync, "interval", hours=1, id="lead_sync") 
    
    scheduler.start()