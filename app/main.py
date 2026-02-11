from fastapi import FastAPI
from dotenv import load_dotenv
from app.core.database import Base, engine
from app.scheduler import start_scheduler, scheduler
from app.workers.youtube.main_worker import run as youtube_worker_run
from app.api import auth, campaigns, dashboard, segments, templates, youtube, stats, categories
from fastapi.middleware.cors import CORSMiddleware

from app.models import *

load_dotenv()


app = FastAPI(title="Glossour Backend")

# -------------------------
# CORS (Allow Frontend Cookies)
# -------------------------
origins = [
    "http://localhost:3000", # Your Frontend URL
    "http://127.0.0.1:3000",
    "https://your-production-domain.com"
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True, # <--- MUST BE TRUE for Cookies
    allow_methods=["*"],
    allow_headers=["*"],
)

# -------------------------
# Include Routers
# -------------------------
app.include_router(auth.router) # Register the new router
app.include_router(categories.router)
app.include_router(youtube.router)
app.include_router(stats.router)
app.include_router(dashboard.router)
app.include_router((segments.router))
app.include_router((campaigns.router))
app.include_router((templates.router))


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
