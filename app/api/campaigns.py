from fastapi import APIRouter, Depends, Query, HTTPException, BackgroundTasks
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from typing import List, Optional
from pydantic import BaseModel

from app.core.database import SessionLocal
from app.services.campaign_service import CampaignService
from app.workers.campaign.email_worker import run_email_campaigns
from app.workers.campaign.ai_generator import run_ai_generation

# Models need to be imported so SQLAlchemy knows them
from app.models.campaign import Campaign, OutreachTemplate

router = APIRouter(prefix="/api", tags=["Campaign Module"])

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# --- Pydantic Request Models ---
class CreateCampaignRequest(BaseModel):
    name: str
    platform: str # 'email' or 'instagram'
    template_id: int
    lead_ids: List[int]

# =========================================================
# 1. LEAD SELECTION APIs
# =========================================================

@router.get("/leads")
def get_leads_table(
    page: int = 1, 
    limit: int = 20, 
    search: str = None, 
    filter: str = None, # 'email', 'instagram'
    db: Session = Depends(get_db)
):
    service = CampaignService(db)
    return service.get_leads_selection(page, limit, search, filter)

@router.get("/leads/kpis")
def get_leads_kpis(db: Session = Depends(get_db)):
    service = CampaignService(db)
    return service.get_lead_kpis()

# =========================================================
# 2. CAMPAIGN APIs
# =========================================================

@router.get("/campaigns/kpis")
def get_campaign_dashboard_kpis(db: Session = Depends(get_db)):
    service = CampaignService(db)
    return service.get_campaign_kpis()

@router.get("/campaigns")
def list_campaigns(db: Session = Depends(get_db)):
    # Return list with basic stats
    return db.query(Campaign).order_by(Campaign.created_at.desc()).all()

@router.get("/campaigns/{campaign_id}")
def get_campaign_detail(campaign_id: int, db: Session = Depends(get_db)):
    campaign = db.query(Campaign).get(campaign_id)
    if not campaign:
        raise HTTPException(404, "Campaign not found")
    # Helper to count leads by status
    stats = {
        "total": len(campaign.leads),
        "sent": sum(1 for l in campaign.leads if l.status == 'sent'),
        "queued": sum(1 for l in campaign.leads if l.status == 'queued'),
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
    
    # If template is AI powered, trigger AI generation immediately
    if new_campaign.template.is_ai_powered:
        background_tasks.add_task(run_ai_generation)
        
    return new_campaign

# =========================================================
# 3. ACTIONS & EXPORT
# =========================================================

@router.post("/campaigns/{campaign_id}/start")
def start_campaign(campaign_id: int, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    campaign = db.query(Campaign).get(campaign_id)
    if not campaign:
        raise HTTPException(404, "Campaign not found")
        
    campaign.status = "running"
    db.commit()
    
    # Trigger the Email Worker
    if campaign.platform == 'email':
        background_tasks.add_task(run_email_campaigns)
        
    return {"status": "running"}

@router.get("/campaigns/{campaign_id}/export")
def export_campaign(campaign_id: int, db: Session = Depends(get_db)):
    service = CampaignService(db)
    csv_file = service.export_campaign_leads(campaign_id)
    
    filename = f"campaign_{campaign_id}_export.csv"
    return StreamingResponse(
        iter([csv_file.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )

# =========================================================
# 4. TEMPLATE API (Helper for creation)
# =========================================================
@router.get("/templates")
def get_templates(db: Session = Depends(get_db)):
    return db.query(OutreachTemplate).all()