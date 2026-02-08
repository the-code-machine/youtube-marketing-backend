from apscheduler.schedulers.background import BackgroundScheduler
from app.workers.youtube.main_worker import run

scheduler = BackgroundScheduler(timezone="UTC")

def start_scheduler():

    scheduler.add_job(
        run,
        trigger="interval",
        minutes=2,          # 👈 runs every 2 minutes
        id="youtube_worker",
        replace_existing=True,
        max_instances=1,    # prevents overlapping jobs
        coalesce=True       # skip missed runs
    )

    scheduler.start()
    print("⏰ Scheduler started (every 2 minutes)")
