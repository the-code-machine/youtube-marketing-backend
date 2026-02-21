import csv
from io import StringIO
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Query, HTTPException, BackgroundTasks
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from app.core.database import SessionLocal

# Services & Workers
from app.models.lead import Lead
from app.models.youtube_channel import YoutubeChannel
from app.models.youtube_video import YoutubeVideo
from app.services.campaign_service import CampaignService
from app.workers.campaign.email_worker import run_email_campaigns
from app.workers.campaign.ai_generator import run_ai_generation

# Models & Schemas
from app.models.campaign import Campaign, CampaignLead
from app.models.email_template import EmailTemplate
from app.schemas.campaign import (
    CreateCampaignRequest,
    LeadSelectionResponse,
    LeadKPIs,
    CampaignKPIs
)

router = APIRouter(prefix="/api", tags=["Campaign Module"])


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# =========================================================
# 1. LEAD SELECTION APIs
# =========================================================

@router.get("/templates")
def get_templates(db: Session = Depends(get_db)):
    return db.query(EmailTemplate).all()


@router.get("/leads", response_model=LeadSelectionResponse)
def get_leads_table(
    # --- Pagination & Search ---
    page: int = 1,
    limit: int = 20,
    search: str = None,

    # --- Existing Filter ---
    filter: str = None,                             # 'email' | 'instagram'

    # --- NEW: Country Filter ---
    country: Optional[str] = Query(None, description="Filter by country code, e.g. US, IN, GB"),

    # --- NEW: Subscriber Range ---
    min_subscribers: Optional[int] = Query(None, description="Minimum subscriber count"),
    max_subscribers: Optional[int] = Query(None, description="Maximum subscriber count"),

    # --- NEW: Video Duration Range (seconds) ---
    min_duration: Optional[int] = Query(None, description="Minimum video duration in seconds (e.g. 60 = 1 min)"),
    max_duration: Optional[int] = Query(None, description="Maximum video duration in seconds (e.g. 3600 = 1 hour)"),

    # --- NEW: Time Range for Latest Leads ---
    date_from: Optional[datetime] = Query(None, description="Filter leads created after this date (ISO format)"),
    date_to: Optional[datetime] = Query(None, description="Filter leads created before this date (ISO format)"),

    # --- NEW: Exclude Already Contacted (Anti-Duplicate) ---
    exclude_contacted: bool = Query(False, description="Set true to hide leads already sent an email/contact"),

    db: Session = Depends(get_db)
):
    service = CampaignService(db)
    return service.get_leads_selection(
        page=page,
        limit=limit,
        search=search,
        filter_type=filter,
        # New filters
        country=country,
        min_subscribers=min_subscribers,
        max_subscribers=max_subscribers,
        min_duration_seconds=min_duration,
        max_duration_seconds=max_duration,
        date_from=date_from,
        date_to=date_to,
        exclude_contacted=exclude_contacted,
    )


@router.get("/leads/kpis", response_model=LeadKPIs)
def get_leads_kpis(db: Session = Depends(get_db)):
    service = CampaignService(db)
    return service.get_lead_kpis()


# =========================================================
# 2. CAMPAIGN MANAGEMENT APIs
# =========================================================

@router.post("/campaigns")
def create_campaign(
    request: CreateCampaignRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    service = CampaignService(db)
    campaign = service.create_campaign(
        name=request.name,
        platform=request.platform,
        template_id=request.template_id,
        lead_ids=request.lead_ids
    )
    background_tasks.add_task(run_ai_generation, campaign.id)
    return {"message": "Campaign created", "campaign_id": campaign.id}


@router.get("/campaigns/kpis", response_model=CampaignKPIs)
def get_campaign_kpis(db: Session = Depends(get_db)):
    service = CampaignService(db)
    return service.get_campaign_kpis()


@router.post("/campaigns/{campaign_id}/run")
def run_campaign(
    campaign_id: int,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    campaign = db.query(Campaign).filter(Campaign.id == campaign_id).first()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")
    campaign.status = "running"
    db.commit()
    background_tasks.add_task(run_email_campaigns)
    return {"message": f"Campaign {campaign_id} started"}


@router.get("/campaigns/{campaign_id}/export")
def export_campaign(campaign_id: int, db: Session = Depends(get_db)):
    service = CampaignService(db)
    output = service.export_campaign_leads(campaign_id)
    return StreamingResponse(
        output,
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=campaign_{campaign_id}_leads.csv"}
    )