from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime

# --- 1. RICH LEAD RESPONSE (For Table) ---
class LeadSelectionItem(BaseModel):
    id: int
    channel_id: str
    video_id: Optional[str] = None

    # Channel Details
    title: Optional[str] = "Unknown Channel"
    thumbnail_url: Optional[str] = None
    channel_url: Optional[str] = None
    subscriber_count: Optional[int] = 0
    country_code: Optional[str] = None          # ← ADDED — was being stripped by Pydantic

    # Video Details
    video_title: Optional[str] = None
    video_thumbnail: Optional[str] = None
    video_url: Optional[str] = None
    duration_seconds: Optional[int] = None      # ← ADDED — was causing blank duration field

    # Contact & Status
    email: Optional[str] = None
    instagram: Optional[str] = None
    status: Optional[str] = "new"
    created_at: Optional[datetime] = None

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
    platform: str  # 'email' or 'instagram'
    template_id: int
    lead_ids: List[int]

# --- 3. KPIS ---
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