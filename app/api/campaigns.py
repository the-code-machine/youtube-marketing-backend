from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session
from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel

from app.core.database import SessionLocal
from app.models.campaign import Campaign, CampaignLead, OutreachTemplate
from app.models.lead import Lead
from app.workers.campaign.email_worker import run_email_campaigns

router = APIRouter(prefix="/campaigns", tags=["Campaigns & Outreach"])

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# --- SCHEMAS ---
class TemplateCreate(BaseModel):
    name: str
    type: str # 'email', 'instagram_dm'
    is_ai_powered: bool = False
    subject_template: Optional[str] = None
    body_template: str

class CampaignCreate(BaseModel):
    name: str
    platform: str
    template_id: int

class AddLeadsRequest(BaseModel):
    lead_ids: List[int] # IDs from the 'leads' table

# --- ROUTES ---

# 1. Templates CRUD
@router.post("/templates")
def create_template(t: TemplateCreate, db: Session = Depends(get_db)):
    new_template = OutreachTemplate(
        name=t.name,
        type=t.type,
        is_ai_powered=t.is_ai_powered,
        subject_template=t.subject_template,
        body_template=t.body_template
    )
    db.add(new_template)
    db.commit()
    db.refresh(new_template)
    return new_template

@router.get("/templates")
def get_templates(db: Session = Depends(get_db)):
    return db.query(OutreachTemplate).all()

# 2. Campaign CRUD
@router.post("/")
def create_campaign(c: CampaignCreate, db: Session = Depends(get_db)):
    # Verify template exists
    template = db.query(OutreachTemplate).get(c.template_id)
    if not template:
        raise HTTPException(404, "Template not found")

    new_campaign = Campaign(
        name=c.name,
        platform=c.platform,
        template_id=c.template_id,
        status="draft"
    )
    db.add(new_campaign)
    db.commit()
    db.refresh(new_campaign)
    return new_campaign

@router.get("/")
def list_campaigns(db: Session = Depends(get_db)):
    # Return campaigns with basic stats
    return db.query(Campaign).all()

# 3. Add Leads to Campaign
@router.post("/{campaign_id}/leads")
def add_leads(campaign_id: int, req: AddLeadsRequest, db: Session = Depends(get_db)):
    campaign = db.query(Campaign).get(campaign_id)
    if not campaign:
        raise HTTPException(404, "Campaign not found")

    added_count = 0
    for lead_id in req.lead_ids:
        # Prevent duplicates
        exists = db.query(CampaignLead).filter(
            CampaignLead.campaign_id == campaign.id,
            CampaignLead.lead_id == lead_id
        ).first()
        
        if exists:
            continue
            
        # Determine initial status
        # If AI is powered, we need to generate first. If not, it's ready.
        initial_status = "queued" if campaign.template.is_ai_powered else "ready_to_send"
        
        link = CampaignLead(
            campaign_id=campaign.id,
            lead_id=lead_id,
            status=initial_status,
            created_at=datetime.utcnow()
        )
        db.add(link)
        added_count += 1
        
    campaign.total_leads += added_count
    db.commit()
    
    return {"status": "success", "added": added_count}

# 4. Trigger Campaign (Start/Pause)
@router.post("/{campaign_id}/status")
def update_status(campaign_id: int, status: str, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    campaign = db.query(Campaign).get(campaign_id)
    if not campaign:
        raise HTTPException(404, "Campaign not found")
        
    if status not in ['draft', 'running', 'paused', 'completed']:
        raise HTTPException(400, "Invalid status")
        
    campaign.status = status
    db.commit()
    
    # If set to running, trigger the worker immediately
    if status == 'running':
        background_tasks.add_task(run_email_campaigns)
        
    return {"status": "updated", "new_status": status}