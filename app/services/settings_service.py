from sqlalchemy.orm import Session
from sqlalchemy import func, desc
from datetime import datetime, timedelta

# Import your models (Ensure these files exist based on your prompt)
from app.models.ai_usage import AIUsageLog
from app.models.email_message import EmailMessage
from app.models.automation_job import AutomationJob 
# Note: If you haven't created separate files for EmailMessage/AutomationJob, 
# put them in app/models/system_logs.py and adjust import.

class SettingsService:
    def __init__(self, db: Session):
        self.db = db

    # --- AI USAGE ---
    def get_ai_logs(self, page: int, limit: int):
        query = self.db.query(AIUsageLog)
        total = query.count()
        results = query.order_by(desc(AIUsageLog.created_at))\
                       .offset((page - 1) * limit)\
                       .limit(limit).all()
        
        return {"data": results, "total": total, "page": page, "limit": limit}

    # --- EMAIL LOGS ---
    def get_email_logs(self, page: int, limit: int):
        query = self.db.query(EmailMessage)
        total = query.count()
        results = query.order_by(desc(EmailMessage.created_at))\
                       .offset((page - 1) * limit)\
                       .limit(limit).all()
        
        return {"data": results, "total": total, "page": page, "limit": limit}

    # --- AUTOMATION JOBS ---
    def get_automation_jobs(self, page: int, limit: int):
        query = self.db.query(AutomationJob)
        total = query.count()
        results = query.order_by(desc(AutomationJob.created_at))\
                       .offset((page - 1) * limit)\
                       .limit(limit).all()
        
        return {"data": results, "total": total, "page": page, "limit": limit}

    # --- SYSTEM KPIS ---
    def get_system_kpis(self):
        # 1. Total AI Cost
        total_cost = self.db.query(func.sum(AIUsageLog.estimated_cost)).scalar() or 0.0
        
        # 2. Emails Sent Today
        today = datetime.utcnow().date()
        emails_today = self.db.query(func.count(EmailMessage.id))\
            .filter(func.date(EmailMessage.sent_at) == today, EmailMessage.status == 'sent').scalar() or 0
            
        # 3. Active Jobs
        active_jobs = self.db.query(func.count(AutomationJob.id))\
            .filter(AutomationJob.status == 'running').scalar() or 0
            
        # 4. Failed Jobs (Last 24h)
        last_24h = datetime.utcnow() - timedelta(hours=24)
        failed_jobs = self.db.query(func.count(AutomationJob.id))\
            .filter(AutomationJob.status == 'failed', AutomationJob.created_at >= last_24h).scalar() or 0

        return {
            "total_ai_cost": round(total_cost, 4),
            "emails_sent_today": emails_today,
            "active_jobs": active_jobs,
            "failed_jobs_24h": failed_jobs
        }