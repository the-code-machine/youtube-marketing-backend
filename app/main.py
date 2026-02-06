from fastapi import FastAPI
from dotenv import load_dotenv
from app.core.database import Base, engine
from app.scheduler import start_scheduler, scheduler
from app.workers.youtube.main_worker import run as youtube_worker_run
from app.api import youtube, stats, categories

# Import ALL models so Alembic + SQLAlchemy see them
from app.models import *

load_dotenv()


app = FastAPI(title="Glossour Backend")

app.include_router(categories.router)
app.include_router(youtube.router)
app.include_router(stats.router)


# -------------------------
# DB INIT
# -------------------------
Base.metadata.create_all(bind=engine)

# -------------------------
# FastAPI lifecycle
# -------------------------

@app.on_event("startup")
def startup():

    start_scheduler()
    print("Scheduler started")

@app.on_event("shutdown")
def shutdown():
    scheduler.shutdown()

# -------------------------
# Routes
# -------------------------

@app.get("/")
def root():
    return {"status": "running"}

# Manual trigger (admin)
@app.post("/run/youtube")
def run_youtube_now():
    youtube_worker_run()
    return {"status": "youtube worker started"}
