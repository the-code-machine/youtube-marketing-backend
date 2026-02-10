from pydantic import BaseModel
from typing import List, Optional, Any, Dict
from datetime import datetime

# --- CARDS ---
class SegmentCard(BaseModel):
    id: str
    title: str
    type: str
    description: Optional[str] = None
    icon: str
    status: str
    total_items: int

# --- KPIS ---
class MetricValue(BaseModel):
    current: int
    previous: int
    change_percent: float
    trend: str 

class SegmentKPIs(BaseModel):
    total_channels: MetricValue
    total_videos: MetricValue
    total_leads: MetricValue
    total_emails: MetricValue
    total_instagram: MetricValue
    responses_received: MetricValue

# --- GRAPH ---
class GraphSeries(BaseModel):
    name: str
    data: List[Dict[str, Any]] # [{x: "2024-01-01", y: 15}]

class GraphResponse(BaseModel):
    granularity: str
    series: List[GraphSeries]

# --- TABLE (UPDATED) ---
class TableRow(BaseModel):
    channel_id: str
    name: str                # Updated from channel_name
    thumbnail_url: Optional[str] = None
    subscribers: int
    video_count: int         # New
    view_count: int          # New
    engagement_score: Optional[float] = None # New
    
    email: Optional[str] = None
    instagram: Optional[str] = None
    
    country: Optional[str] = None
    category_name: str
    fetched_at: datetime

class TableResponse(BaseModel):
    page: int
    limit: int
    total: int
    data: List[TableRow]

# --- AI STUB ---
class AIStubResponse(BaseModel):
    summary: str
    key_insights: List[str]
    suggested_actions: List[str]