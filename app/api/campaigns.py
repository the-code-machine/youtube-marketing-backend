import csv
from io import StringIO
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
    LeadSelectionResponse, # <--- Updated Schema
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
# Update the get_templates endpoint:
@router.get("/templates")
def get_templates(db: Session = Depends(get_db)):
    return db.query(EmailTemplate).all()

@router.get("/leads", response_model=LeadSelectionResponse)
def get_leads_table(
    page: int = 1, 
    limit: int = 20, 
    search: str = None, 
    filter: str = None, 
    db: Session = Depends(get_db)
):
    service = CampaignService(db)
    return service.get_leads_selection(page, limit, search, filter)

@router.get("/leads/kpis", response_model=LeadKPIs)
def get_leads_kpis(db: Session = Depends(get_db)):
    service = CampaignService(db)
    return service.get_lead_kpis()

# =========================================================
# 2. CAMPAIGN APIs
# =========================================================

@router.get("/campaigns/kpis", response_model=CampaignKPIs)
def get_campaign_dashboard_kpis(db: Session = Depends(get_db)):
    service = CampaignService(db)
    return service.get_campaign_kpis()

@router.get("/campaigns")
def list_campaigns(db: Session = Depends(get_db)):
    return db.query(Campaign).order_by(Campaign.created_at.desc()).all()

@router.get("/campaigns/{campaign_id}")
def get_campaign_detail(campaign_id: int, db: Session = Depends(get_db)):
    campaign = db.query(Campaign).get(campaign_id)
    if not campaign:
        raise HTTPException(404, "Campaign not found")
    
    # Calculate live stats
    stats = {
        "total": len(campaign.leads),
        "sent": sum(1 for l in campaign.leads if l.status == 'sent'),
        "queued": sum(1 for l in campaign.leads if l.status == 'queued'),
        "review_ready": sum(1 for l in campaign.leads if l.status == 'review_ready'),
        "failed": sum(1 for l in campaign.leads if l.status == 'failed'),
    }
    return {"campaign": campaign, "stats": stats}

@router.post("/campaigns")
def create_campaign(
    payload: CreateCampaignRequest, 
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    service = CampaignService(db)
    new_campaign = service.create_campaign(
        payload.name, 
        payload.platform, 
        payload.template_id, 
        payload.lead_ids
    )
    
    # ✅ FIX: Always trigger the worker. 
    # If the queue is empty, the worker just exits instantly (no harm done).
    # If leads are queued, it starts processing immediately.
    background_tasks.add_task(run_ai_generation)
        
    return new_campaign

# =========================================================
# 3. ACTIONS
# =========================================================

@router.post("/campaigns/{campaign_id}/start")
def start_campaign(campaign_id: int, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    campaign = db.query(Campaign).get(campaign_id)
    if not campaign:
        raise HTTPException(404, "Campaign not found")
        
    campaign.status = "running"
    db.commit()
    
    # Trigger Email Worker
    if campaign.platform == 'email':
        background_tasks.add_task(run_email_campaigns)
        
    return {"status": "running"}

@router.get("/campaigns/{campaign_id}/export")
def export_campaign_leads(self, campaign_id: int):
    results = self.db.query(
        YoutubeChannel.name,
        YoutubeVideo.title,
        Lead.channel_id,
        Lead.video_id,
        Lead.primary_email,
        Lead.instagram_username,
        CampaignLead.status
    ).join(CampaignLead, Lead.id == CampaignLead.lead_id)\
     .outerjoin(YoutubeChannel, Lead.channel_id == YoutubeChannel.channel_id)\
     .outerjoin(YoutubeVideo, Lead.video_id == YoutubeVideo.video_id)\
     .filter(CampaignLead.campaign_id == campaign_id).all()

    output = StringIO()
    writer = csv.writer(output)
    # Added Video Title and URLs to CSV header
    writer.writerow(["Channel Name", "Video Title", "Channel URL", "Video URL", "Email", "Instagram", "Status"])
    
    for r in results:
        writer.writerow([
            r.name, 
            r.title, 
            f"https://youtube.com/channel/{r.channel_id}",
            f"https://youtube.com/watch?v={r.video_id}",
            r.primary_email, 
            r.instagram_username, 
            r.status
        ])
        
    output.seek(0)
    return output
