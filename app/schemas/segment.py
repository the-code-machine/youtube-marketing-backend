from pydantic import BaseModel
from typing import List, Optional, Any, Dict
from datetime import datetime

class SegmentCard(BaseModel):
    id: str # Can be "1" (DB ID) or "filter_subs_high" (Logic ID)
    title: str
    type: str # "youtube_category" | "filter" | "ai_group"
    description: Optional[str] = None
    icon: str # Frontend icon name (e.g. "music", "clock", "globe")
    status: str # "active" | "disabled"
    total_items: int

class MetricValue(BaseModel):
    current: int
    previous: int
    change_percent: float
    trend: str # 'up', 'down', 'neutral'

class SegmentKPIs(BaseModel):
    total_channels: MetricValue
    total_videos: MetricValue
    total_leads: MetricValue
    total_emails: MetricValue
    total_instagram: MetricValue
    responses_received: MetricValue

class GraphSeries(BaseModel):
    name: str
    data: List[Dict[str, Any]] # [{x: timestamp, y: value}]

class GraphResponse(BaseModel):
    granularity: str
    series: List[GraphSeries]

class TableRow(BaseModel):
    channel_id: str
    channel_name: str
    subscribers: int
    email: Optional[str] = None
    instagram: Optional[str] = None
    duration_avg: Optional[int] = None
    country: Optional[str] = None
    category_name: str
    fetched_at: datetime

class TableResponse(BaseModel):
    page: int
    limit: int
    total: int
    data: List[TableRow]

class AIStubResponse(BaseModel):
    summary: str
    key_insights: List[str]
    suggested_actions: List[str]