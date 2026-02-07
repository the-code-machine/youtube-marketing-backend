from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import desc, asc, or_
from typing import Optional, List
from app.core.database import SessionLocal
from app.models import YoutubeChannel, YoutubeVideo, ExtractedEmail, Lead

router = APIRouter(prefix="/youtube", tags=["Youtube Data"])

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# ---------------------------------------------------------
# 1. SMART CHANNELS ENDPOINT (Search, Sort, Filter)
# ---------------------------------------------------------
@router.get("/channels")
def get_channels(
    db: Session = Depends(get_db),
    page: int = 1,
    page_size: int = 20,
    search: Optional[str] = None,
    min_subs: Optional[int] = None,
    has_email: Optional[bool] = None,
    country: Optional[str] = None,
    sort_by: str = "subscriber_count",
    sort_order: str = "desc"
):
    """
    Fetch channels with server-side pagination and filtering.
    """
    query = db.query(YoutubeChannel)

    # --- FILTERS ---
    if search:
        # Case-insensitive search on Name or Handle
        query = query.filter(
            or_(
                YoutubeChannel.name.ilike(f"%{search}%"),
                YoutubeChannel.handle.ilike(f"%{search}%")
            )
        )
    
    if min_subs:
        query = query.filter(YoutubeChannel.subscriber_count >= min_subs)
    
    if has_email is not None:
        query = query.filter(YoutubeChannel.has_email == has_email)
        
    if country:
        query = query.filter(YoutubeChannel.country_code == country)

    # --- SORTING ---
    # Map sort string to actual column
    sort_column = getattr(YoutubeChannel, sort_by, YoutubeChannel.subscriber_count)
    
    if sort_order == "asc":
        query = query.order_by(asc(sort_column))
    else:
        query = query.order_by(desc(sort_column))

    # --- PAGINATION ---
    total_count = query.count()
    offset = (page - 1) * page_size
    channels = query.offset(offset).limit(page_size).all()

    return {
        "data": channels,
        "total": total_count,
        "page": page,
        "page_size": page_size,
        "total_pages": (total_count + page_size - 1) // page_size
    }

# ---------------------------------------------------------
# 2. VIDEOS ENDPOINT (Contextual)
# ---------------------------------------------------------
@router.get("/videos")
def get_videos(
    db: Session = Depends(get_db),
    channel_id: Optional[str] = None,
    page: int = 1,
    page_size: int = 20
):
    query = db.query(YoutubeVideo)

    if channel_id:
        query = query.filter(YoutubeVideo.channel_id == channel_id)

    total_count = query.count()
    videos = query.order_by(YoutubeVideo.published_at.desc())\
                  .offset((page - 1) * page_size)\
                  .limit(page_size)\
                  .all()

    return {
        "data": videos,
        "total": total_count,
        "page": page
    }

# ---------------------------------------------------------
# 3. LEADS MANAGER (Kanban/Table View Optimized)
# ---------------------------------------------------------
@router.get("/leads")
def get_leads(
    db: Session = Depends(get_db),
    status: Optional[str] = None,  # 'new', 'contacted', 'replied'
    page: int = 1,
    page_size: int = 50
):
    query = db.query(Lead)

    if status:
        query = query.filter(Lead.status == status)

    # Join with Channel to get the Name/Avatar for the UI
    # We select specific columns to keep the query fast
    results = db.query(
        Lead, 
        YoutubeChannel.name, 
        YoutubeChannel.thumbnail_url,
        YoutubeChannel.subscriber_count
    ).join(YoutubeChannel, Lead.channel_id == YoutubeChannel.channel_id)\
     .order_by(Lead.created_at.desc())\
     .offset((page - 1) * page_size)\
     .limit(page_size)\
     .all()

    # Format for frontend
    data = []
    for lead, name, thumb, subs in results:
        lead_dict = lead.__dict__
        lead_dict["channel_name"] = name
        lead_dict["channel_thumbnail"] = thumb
        lead_dict["subscriber_count"] = subs
        data.append(lead_dict)

    return {"data": data, "page": page}

# ---------------------------------------------------------
# 4. EXPORT ENDPOINT (For CSV/Excel)
# ---------------------------------------------------------
@router.get("/export/emails")
def get_all_emails(db: Session = Depends(get_db)):
    """Returns ALL distinct emails for download"""
    return db.query(ExtractedEmail.email, ExtractedEmail.channel_id).distinct().all()