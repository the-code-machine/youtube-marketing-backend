from pydantic import BaseModel
from typing import List, Optional, Dict, Any, Union
from datetime import datetime

# --- GENERIC BUILDING BLOCKS ---
class MetricChange(BaseModel):
    value: int
    previous_value: int
    percentage_change: float
    trend: str # 'up', 'down', 'neutral'

class TimeSeriesPoint(BaseModel):
    timestamp: datetime
    label: str # "10:00 AM" or "Feb 10"
    value: int
    category: Optional[str] = None # For multi-line graphs

# --- KPI RESPONSES ---
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

class CombinedKPIs(DataKPIs, LeadKPIs):
    pass

# --- API RESPONSES ---
class KpiResponse(BaseModel):
    view_mode: str
    data: Union[DataKPIs, LeadKPIs, CombinedKPIs]

class MainGraphResponse(BaseModel):
    view_mode: str
    granularity: str
    series: List[TimeSeriesPoint]

class MiniGraphResponse(BaseModel):
    metric_name: str
    data: List[TimeSeriesPoint]

class SystemStatusResponse(BaseModel):
    last_worker_run: datetime
    last_lead_update: datetime
    system_health: str