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
    # contact filter: 'email' | 'instagram' | 'both'
    filter: str = None,
    country: Optional[str] = Query(None),
    min_subscribers: Optional[int] = Query(None),
    max_subscribers: Optional[int] = Query(None),
    min_duration: Optional[int] = Query(None),
    max_duration: Optional[int] = Query(None),
    date_from: Optional[datetime] = Query(None),
    date_to: Optional[datetime] = Query(None),
    exclude_contacted: bool = Query(False),
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
    campaigns = db.query(Campaign).order_by(Campaign.created_at.desc()).all()
    result = []
    for c in campaigns:
        leads       = c.leads or []
        leads_count = len(leads) if leads else (c.total_leads or 0)
        sent_count  = sum(1 for l in leads if l.status == "sent") if leads else (c.sent_count or 0)
        result.append({
            "id":          c.id,
            "name":        c.name,
            "platform":    c.platform,
            "status":      c.status,
            "leads_count": leads_count,
            "sent_count":  sent_count,
            "total_leads": c.total_leads,
            "created_at":  c.created_at,
            "updated_at":  c.updated_at,
        })
    return result


@router.get("/campaigns/kpis", response_model=CampaignKPIs)
def get_campaign_kpis(db: Session = Depends(get_db)):
    return CampaignService(db).get_campaign_kpis()


@router.get("/campaigns/{campaign_id}")
def get_campaign_detail(campaign_id: int, db: Session = Depends(get_db)):
    """Full campaign detail with leads and live stats. Used by detail page."""
    campaign = db.query(Campaign).filter(Campaign.id == campaign_id).first()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")

    leads = campaign.leads or []
    stats = {
        "total":        len(leads),
        "queued":       sum(1 for l in leads if l.status in ("queued", "processing_ai")),
        "review_ready": sum(1 for l in leads if l.status in ("review_ready", "ready_to_send")),
        "sent":         sum(1 for l in leads if l.status == "sent"),
        "failed":       sum(1 for l in leads if l.status == "failed"),
    }
    return {"campaign": campaign, "stats": stats}


# =========================================================
# 4. CAMPAIGN ACTIONS
# =========================================================

@router.post("/campaigns")
def create_campaign(
    request: CreateCampaignRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """
    Creates campaign + queues AI generation.
    Returns full campaign object — frontend accesses res.data.id
    """
    campaign = CampaignService(db).create_campaign(
        name=request.name,
        platform=request.platform,
        template_id=request.template_id,
        lead_ids=request.lead_ids,
    )
    background_tasks.add_task(run_ai_generation)
    return campaign  # ORM object serialized by FastAPI → res.data.id works


@router.post("/campaigns/{campaign_id}/start")
def start_campaign(
    campaign_id: int,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """Start transmission for a campaign that has AI-ready leads."""
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
        headers={"Content-Disposition": f"attachment; filename=campaign_{campaign_id}_leads.csv"},
    )