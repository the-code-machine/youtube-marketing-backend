from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime

# --- TABLE ROW ITEM ---
class AIStoreItem(BaseModel):
    id: int # CampaignLead ID
    campaign_name: str
    
    # Channel Info
    channel_id: str
    channel_title: str
    thumbnail_url: Optional[str] = None
    subscriber_count: int = 0
    
    # AI Content
    ai_subject: Optional[str] = None
    ai_body: Optional[str] = None
    status: str # 'queued', 'review_ready', 'sent', 'failed'
    
    generated_at: Optional[datetime] = None
    
    class Config:
        from_attributes = True

# --- PAGINATED RESPONSE ---
class AIStoreResponse(BaseModel):
    data: List[AIStoreItem]
    total: int
    page: int
    limit: int

# --- KPI STATS ---
class AIStoreKPIs(BaseModel):
    total_generated: int
    waiting_review: int
    approved_sent: int
    total_words_generated: int # Proxy for "Usage"