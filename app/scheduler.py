# app/scheduler.py
import logging
from apscheduler.schedulers.background import BackgroundScheduler

logger = logging.getLogger(__name__)
scheduler = BackgroundScheduler()

def start_scheduler():
    if scheduler.running:
        return

    from app.workers.youtube.main_worker import run as run_youtube
    from app.workers.campaign.ai_generator import run_ai_generation
    from app.workers.campaign.email_worker import run_email_campaigns
    from app.workers.pruner import run as run_pruner

    scheduler.add_job(run_youtube,        "interval", hours=2,   id="youtube",  max_instances=1)
    scheduler.add_job(run_ai_generation,  "interval", minutes=15, id="ai_gen",  max_instances=1)
    scheduler.add_job(run_email_campaigns,"interval", minutes=20, id="email",   max_instances=1)
    scheduler.add_job(run_pruner,         "cron",     hour=3,     id="pruner",  max_instances=1)

    scheduler.start()
    logger.info("Scheduler started — youtube=2h, ai=15m, email=20m, pruner=3am")

def shutdown_scheduler():
    if scheduler.running:
        scheduler.shutdown()