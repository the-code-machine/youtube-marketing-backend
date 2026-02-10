from pydantic import BaseModel
from typing import List, Optional, Union
from datetime import datetime

# --- BASIC BLOCKS ---
class MetricChange(BaseModel):
    value: int
    previous_value: int
    percentage_change: float
    trend: str 

class TimeSeriesPoint(BaseModel):
    timestamp: datetime
    label: str
    value: int
    category: Optional[str] = None # Essential for Combined Graph

# --- KPI STRUCTURES ---
class DataKPIs(BaseModel):
    total_channels: MetricChange
    total_videos: MetricChange
    total_emails: MetricChange
    total_instagram: MetricChange
    total_socials: MetricChange

class LeadKPIs(BaseModel):
    total_leads: MetricChange
    emails_sent: MetricChange
    instagram_dms: MetricChange
    responses_received: MetricChange

class CombinedKPIs(BaseModel):
    # We must explicitly list all fields to avoid Pydantic inheritance issues
    total_channels: Optional[MetricChange] = None
    total_videos: Optional[MetricChange] = None
    total_emails: Optional[MetricChange] = None
    total_instagram: Optional[MetricChange] = None
    total_socials: Optional[MetricChange] = None
    total_leads: Optional[MetricChange] = None
    emails_sent: Optional[MetricChange] = None
    instagram_dms: Optional[MetricChange] = None
    responses_received: Optional[MetricChange] = None

# --- API RESPONSES ---
class KpiResponse(BaseModel):
    view_mode: str
    data: Union[DataKPIs, LeadKPIs, CombinedKPIs]

class MainGraphResponse(BaseModel):
    view_mode: str
    granularity: str
    series: List[TimeSeriesPoint]

class MiniGraphResponse(BaseModel):
    view_mode: str
    graphs: dict[str, List[TimeSeriesPoint]]