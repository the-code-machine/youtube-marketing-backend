from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime

# --- 1. RICH LEAD RESPONSE (For Table) ---
class LeadSelectionItem(BaseModel):
    id: int               # Lead ID (for selection)
    channel_id: str       # YouTube Channel ID
    title: str            # Channel Name/Title
    thumbnail_url: Optional[str] = None
    
    # Metrics
    subscriber_count: Optional[int] = 0
    video_count: Optional[int] = 0
    
    # Contact Info
    email: Optional[str] = None
    instagram: Optional[str] = None
    
    status: str
    created_at: datetime

    class Config:
        from_attributes = True

class LeadSelectionResponse(BaseModel):
    data: List[LeadSelectionItem]
    total: int
    page: int
    limit: int

# --- 2. CAMPAIGN CREATION ---
class CreateCampaignRequest(BaseModel):
    name: str
    platform: str # 'email' or 'instagram'
    template_id: int
    lead_ids: List[int]

# --- 3. KPI ---
class LeadKPIs(BaseModel):
    total_leads: int
    email_leads: int
    instagram_leads: int
    contacted_leads: int

class CampaignKPIs(BaseModel):
    total_campaigns: int
    active_campaigns: int
    emails_sent: int
    responses: int