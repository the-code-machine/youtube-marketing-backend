from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.core.database import SessionLocal
from app.models import YoutubeChannel, YoutubeVideo, ExtractedEmail, Lead

router = APIRouter(prefix="/youtube", tags=["Youtube"])


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# Channels Screen
@router.get("/channels")
def get_channels(db: Session = Depends(get_db)):
    return db.query(YoutubeChannel).order_by(YoutubeChannel.created_at.desc()).limit(500).all()


# Videos Screen
@router.get("/videos")
def get_videos(db: Session = Depends(get_db)):
    return db.query(YoutubeVideo).order_by(YoutubeVideo.published_at.desc()).limit(500).all()


# Emails Screen
@router.get("/emails")
def get_emails(db: Session = Depends(get_db)):
    return db.query(ExtractedEmail).all()


# Leads Screen
@router.get("/leads")
def get_leads(db: Session = Depends(get_db)):
    return db.query(Lead).order_by(Lead.created_at.desc()).all()


# Only HOT Leads (email OR instagram)
@router.get("/leads/hot")
def hot_leads(db: Session = Depends(get_db)):
    return db.query(Lead).filter(
        (Lead.primary_email != None) | (Lead.instagram_username != None)
    ).all()
