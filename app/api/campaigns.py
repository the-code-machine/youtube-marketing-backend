"""
app/api/campaigns.py

Changes vs original:
  - /api/leads now accepts  unique_channels: bool  query param.
    When True → only one lead per channel_id is returned (most recent),
    so the same creator never appears twice in the campaign builder table.
"""

import csv
from io import StringIO
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Query, HTTPException, BackgroundTasks
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from app.core.database import SessionLocal

from app.models.lead import Lead
from app.models.youtube_channel import YoutubeChannel
from app.models.youtube_video import YoutubeVideo
from app.services.campaign_service import CampaignService
from app.workers.campaign.email_worker import run_email_campaigns
from app.workers.campaign.ai_generator import run_ai_generation
from app.models.campaign import Campaign, CampaignLead
from app.models.email_template import EmailTemplate
from app.schemas.campaign import (
    CreateCampaignRequest,
    LeadSelectionResponse,
    LeadKPIs,
    CampaignKPIs,
)

router = APIRouter(prefix="/api", tags=["Campaign Module"])


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# =========================================================
# 1. TEMPLATES
# =========================================================

@router.get("/templates")
def get_templates(db: Session = Depends(get_db)):
    return db.query(EmailTemplate).all()


# =========================================================
# 2. LEAD SELECTION
# =========================================================

@router.get("/leads", response_model=LeadSelectionResponse)
def get_leads_table(
    page: int = 1,
    limit: int = 20,
    search: str = None,
    filter: str = None,                                # 'email' | 'instagram' | 'both'
    country: Optional[str] = Query(None),
    min_subscribers: Optional[int] = Query(None),
    max_subscribers: Optional[int] = Query(None),
    min_duration: Optional[int] = Query(None),
    max_duration: Optional[int] = Query(None),
    date_from: Optional[datetime] = Query(None),
    date_to: Optional[datetime] = Query(None),
    exclude_contacted: bool = Query(False),
    # NEW ─────────────────────────────────────────────────────────────────────
    # When True: deduplicate by channel_id (one lead per channel).
    # This prevents adding the same creator to a campaign multiple times
    # because they had multiple videos in the leads table.
    unique_channels: bool = Query(
        False,
        description="Return only one lead per YouTube channel (the most recent)."
    ),
    # ─────────────────────────────────────────────────────────────────────────
    db: Session = Depends(get_db),
):
    service = CampaignService(db)
    return service.get_leads_selection(
        page=page,
        limit=limit,
        search=search,
        filter_type=filter,
        country=country,
        min_subscribers=min_subscribers,
        max_subscribers=max_subscribers,
        min_duration_seconds=min_duration,
        max_duration_seconds=max_duration,
        date_from=date_from,
        date_to=date_to,
        exclude_contacted=exclude_contacted,
        unique_channels=unique_channels,    # NEW
    )


@router.get("/leads/kpis", response_model=LeadKPIs)
def get_leads_kpis(db: Session = Depends(get_db)):
    return CampaignService(db).get_lead_kpis()


# =========================================================
# 3. CAMPAIGNS — LIST & DETAIL
# =========================================================

@router.get("/campaigns")
def list_campaigns(db: Session = Depends(get_db)):
    """List all campaigns with live sent/total counts for the table."""
    campaigns = db.query(Campaign).order_by(Campaign.id.desc()).all()
    result = []
    for c in campaigns:
        sent = db.query(CampaignLead).filter(
            CampaignLead.campaign_id == c.id,
            CampaignLead.status == "sent"
        ).count()
        result.append({
            **c.__dict__,
            "sent_count": sent,
        })
    return result


@router.get("/campaigns/{campaign_id}")
def get_campaign(campaign_id: int, db: Session = Depends(get_db)):
    campaign = db.query(Campaign).filter(Campaign.id == campaign_id).first()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")
    return campaign


# =========================================================
# 4. CAMPAIGN ACTIONS
# =========================================================

@router.post("/campaigns")
def create_campaign(
    request: CreateCampaignRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    campaign = CampaignService(db).create_campaign(
        name=request.name,
        platform=request.platform,
        template_id=request.template_id,
        lead_ids=request.lead_ids,
        generation_mode=request.generation_mode,
        script_plan_id=request.script_plan_id,
    )
    background_tasks.add_task(run_ai_generation)
    return campaign


@router.post("/campaigns/{campaign_id}/start")
def start_campaign(
    campaign_id: int,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    campaign = db.query(Campaign).filter(Campaign.id == campaign_id).first()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")
    campaign.status = "running"
    db.commit()
    if campaign.platform == "email":
        background_tasks.add_task(run_email_campaigns)
    return {"status": "running", "campaign_id": campaign_id}


@router.post("/campaigns/{campaign_id}/run")
def run_campaign(
    campaign_id: int,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """Alias for /start — backward compatibility."""
    return start_campaign(campaign_id, background_tasks, db)


# =========================================================
# 5. EXPORT
# =========================================================

@router.get("/campaigns/{campaign_id}/export")
def export_campaign(campaign_id: int, db: Session = Depends(get_db)):
    output = CampaignService(db).export_campaign_leads(campaign_id)
    return StreamingResponse(
        output,
        media_type="text/csv",
        headers={
            "Content-Disposition": f"attachment; filename=campaign_{campaign_id}_leads.csv"
        },
    )


# =========================================================
# 6. KPIs
# =========================================================

@router.get("/campaigns/kpis", response_model=CampaignKPIs)
def get_campaign_kpis(db: Session = Depends(get_db)):
    return CampaignService(db).get_campaign_kpis()