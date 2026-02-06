from apscheduler.schedulers.background import BackgroundScheduler
from app.workers.youtube.main_worker import run

scheduler = BackgroundScheduler()

def start_scheduler():
    scheduler.add_job(run, "interval", hours=3)
    scheduler.start()
