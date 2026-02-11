from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime

# --- AI USAGE ---
class AIUsageLogSchema(BaseModel):
    id: int
    task_type: str
    model_name: Optional[str]
    total_tokens: int
    estimated_cost: float
    related_channel_id: Optional[str]
    status: str
    created_at: datetime

    class Config:
        from_attributes = True

class AIUsageResponse(BaseModel):
    data: List[AIUsageLogSchema]
    total: int
    page: int
    limit: int

# --- EMAIL LOGS ---
class EmailMessageSchema(BaseModel):
    id: int
    lead_id: Optional[int]
    email: str
    subject: str
    status: str # sent, failed
    provider: Optional[str]
    sent_at: Optional[datetime]
    created_at: datetime

    class Config:
        from_attributes = True

class EmailLogResponse(BaseModel):
    data: List[EmailMessageSchema]
    total: int
    page: int
    limit: int

# --- AUTOMATION JOBS ---
class AutomationJobSchema(BaseModel):
    id: int
    job_type: str
    status: str # running, completed, failed
    started_at: Optional[datetime]
    finished_at: Optional[datetime]
    error_message: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True

class AutomationJobResponse(BaseModel):
    data: List[AutomationJobSchema]
    total: int
    page: int
    limit: int

# --- DASHBOARD KPI ---
class SystemKPIs(BaseModel):
    total_ai_cost: float
    emails_sent_today: int
    active_jobs: int
    failed_jobs_24h: int