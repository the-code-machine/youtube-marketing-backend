"""
app/api/campaigns.py

Fixes:
  1. /campaigns/kpis MUST be defined BEFORE /campaigns/{campaign_id}
     otherwise FastAPI tries to cast "kpis" to int → 422
  2. GET /campaigns/{id} now returns {campaign, stats} structure
     that the frontend CampaignDetailPage expects
"""

from io import StringIO
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Query, HTTPException, BackgroundTasks
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from sqlalchemy import func, case

from app.core.database import SessionLocal
from app.models.campaign import Campaign, CampaignLead
from app.models.email_template import EmailTemplate
from app.models.lead import Lead
from app.models.youtube_channel import YoutubeChannel
from app.services.campaign_service import CampaignService
from app.workers.campaign.email_worker import run_email_campaigns
from app.workers.campaign.ai_generator import run_ai_generation

router = APIRouter(prefix="/api", tags=["Campaign Module"])


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# =========================================================
# TEMPLATES
# =========================================================

@router.get("/templates")
def get_templates(db: Session = Depends(get_db)):
    return db.query(EmailTemplate).all()


# =========================================================
# LEADS
# =========================================================

@router.get("/leads")
def get_leads_table(
    page: int = 1,
    limit: int = 20,
    search: str = None,
    filter: str = None,
    country: Optional[str] = Query(None),
    min_subscribers: Optional[int] = Query(None),
    max_subscribers: Optional[int] = Query(None),
    min_duration: Optional[int] = Query(None),
    max_duration: Optional[int] = Query(None),
    date_from: Optional[datetime] = Query(None),
    date_to: Optional[datetime] = Query(None),
    exclude_contacted: bool = Query(False),
    unique_channels: bool = Query(False),
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
        unique_channels=unique_channels,
    )


@router.get("/leads/kpis")
def get_leads_kpis(db: Session = Depends(get_db)):
    return CampaignService(db).get_lead_kpis()


# =========================================================
# CAMPAIGNS — FIXED ROUTE ORDER
# Static routes (/kpis, /list) MUST come before /{campaign_id}
# =========================================================

@router.get("/campaigns/kpis")
def get_campaign_kpis(db: Session = Depends(get_db)):
    """
    MUST be defined before /campaigns/{campaign_id}.
    Previously caused 422 because FastAPI matched /{campaign_id} first
    and tried to cast "kpis" as integer.
    """
    return CampaignService(db).get_campaign_kpis()


@router.get("/campaigns")
def list_campaigns(db: Session = Depends(get_db)):
    campaigns = db.query(Campaign).order_by(Campaign.id.desc()).all()
    result = []
    for c in campaigns:
        sent = (
            db.query(func.count(CampaignLead.id))
            .filter(CampaignLead.campaign_id == c.id, CampaignLead.status == "sent")
            .scalar()
        )
        d = {col.name: getattr(c, col.name) for col in c.__table__.columns}
        d["sent_count"] = sent
        result.append(d)
    return result


@router.get("/campaigns/{campaign_id}")
def get_campaign(campaign_id: int, db: Session = Depends(get_db)):
    """
    Returns { campaign, stats } — the nested structure the frontend expects.
    Previously returned a flat Campaign object with no stats or leads.
    """
    campaign = db.query(Campaign).filter(Campaign.id == campaign_id).first()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")

    # ── Lead status counts (single query with CASE WHEN) ──────────────────
    counts = (
        db.query(
            func.count(CampaignLead.id).label("total"),
            func.count(case((CampaignLead.status == "queued",       CampaignLead.id))).label("queued"),
            func.count(case((CampaignLead.status == "review_ready", CampaignLead.id))).label("review_ready"),
            func.count(case((CampaignLead.status == "sent",         CampaignLead.id))).label("sent"),
            func.count(case((CampaignLead.status == "failed",       CampaignLead.id))).label("failed"),
            func.count(case((CampaignLead.status == "skipped_today",CampaignLead.id))).label("skipped"),
        )
        .filter(CampaignLead.campaign_id == campaign_id)
        .one()
    )

    # ── Load campaign leads with lead contact info ─────────────────────────
    leads_rows = (
        db.query(
            CampaignLead.id,
            CampaignLead.lead_id,
            CampaignLead.status,
            CampaignLead.ai_generated_subject,
            CampaignLead.ai_generated_body,
            CampaignLead.sent_at,
            CampaignLead.error_message,
            Lead.primary_email,
            Lead.instagram_username,
            Lead.channel_id,
            YoutubeChannel.name.label("channel_name"),
            YoutubeChannel.thumbnail_url,
            YoutubeChannel.subscriber_count,
        )
        .join(Lead, CampaignLead.lead_id == Lead.id)
        .outerjoin(YoutubeChannel, Lead.channel_id == YoutubeChannel.channel_id)
        .filter(CampaignLead.campaign_id == campaign_id)
        .order_by(CampaignLead.id)
        .all()
    )

    leads_data = [
        {
            "id":                    r.id,
            "lead_id":               r.lead_id,
            "status":                r.status,
            "ai_generated_subject":  r.ai_generated_subject,
            "ai_generated_body":     r.ai_generated_body,
            "sent_at":               r.sent_at,
            "error_message":         r.error_message,
            "email":                 r.primary_email,
            "instagram":             r.instagram_username,
            "channel_id":            r.channel_id,
            "channel_name":          r.channel_name,
            "thumbnail_url":         r.thumbnail_url,
            "subscriber_count":      r.subscriber_count,
        }
        for r in leads_rows
    ]

    # ── Template info ──────────────────────────────────────────────────────
    template = None
    if campaign.template_id:
        t = db.query(EmailTemplate).filter(EmailTemplate.id == campaign.template_id).first()
        if t:
            template = {col.name: getattr(t, col.name) for col in t.__table__.columns}

    # ── Build response ─────────────────────────────────────────────────────
    campaign_dict = {col.name: getattr(campaign, col.name) for col in campaign.__table__.columns}
    campaign_dict["email_template"] = template
    campaign_dict["leads"] = leads_data

    return {
        "campaign": campaign_dict,
        "stats": {
            "total":        counts.total,
            "queued":       counts.queued,
            "review_ready": counts.review_ready,
            "sent":         counts.sent,
            "failed":       counts.failed,
            "skipped":      counts.skipped,
        },
    }


# =========================================================
# CAMPAIGN ACTIONS
# =========================================================

@router.post("/campaigns")
def create_campaign(request: dict, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    campaign = CampaignService(db).create_campaign(
        name=request.get("name"),
        platform=request.get("platform"),
        template_id=request.get("template_id"),
        lead_ids=request.get("lead_ids", []),
        generation_mode=request.get("generation_mode", "generalised"),
        script_plan_id=request.get("script_plan_id"),
    )
    background_tasks.add_task(run_ai_generation)
    return campaign


@router.post("/campaigns/{campaign_id}/start")
def start_campaign(campaign_id: int, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    campaign = db.query(Campaign).filter(Campaign.id == campaign_id).first()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")
    campaign.status = "running"
    db.commit()
    if campaign.platform == "email":
        background_tasks.add_task(run_email_campaigns)
    return {"status": "running", "campaign_id": campaign_id}


@router.post("/campaigns/{campaign_id}/run")
def run_campaign(campaign_id: int, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    return start_campaign(campaign_id, background_tasks, db)


# =========================================================
# EXPORT
# =========================================================

@router.get("/campaigns/{campaign_id}/export")
def export_campaign(campaign_id: int, db: Session = Depends(get_db)):
    output = CampaignService(db).export_campaign_leads(campaign_id)
    return StreamingResponse(
        output,
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=campaign_{campaign_id}_leads.csv"},
    )