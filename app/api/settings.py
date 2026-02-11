from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.core.database import SessionLocal
from app.services.settings_service import SettingsService
from app.schemas.settings import (
    AIUsageResponse, 
    EmailLogResponse, 
    AutomationJobResponse,
    SystemKPIs
)

router = APIRouter(prefix="/api/settings", tags=["Settings & Logs"])

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@router.get("/kpis", response_model=SystemKPIs)
def get_dashboard_stats(db: Session = Depends(get_db)):
    service = SettingsService(db)
    return service.get_system_kpis()

@router.get("/ai-logs", response_model=AIUsageResponse)
def get_ai_usage(page: int = 1, limit: int = 20, db: Session = Depends(get_db)):
    service = SettingsService(db)
    return service.get_ai_logs(page, limit)

@router.get("/email-logs", response_model=EmailLogResponse)
def get_email_logs(page: int = 1, limit: int = 20, db: Session = Depends(get_db)):
    service = SettingsService(db)
    return service.get_email_logs(page, limit)

@router.get("/jobs", response_model=AutomationJobResponse)
def get_automation_jobs(page: int = 1, limit: int = 20, db: Session = Depends(get_db)):
    service = SettingsService(db)
    return service.get_automation_jobs(page, limit)