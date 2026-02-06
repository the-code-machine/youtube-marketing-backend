from sqlalchemy import Column, Integer, String, Text, TIMESTAMP
from app.core.database import Base

class AutomationJob(Base):
    __tablename__ = "automation_jobs"

    id = Column(Integer, primary_key=True, index=True)

    job_type = Column(String)
    status = Column(String)

    started_at = Column(TIMESTAMP)
    finished_at = Column(TIMESTAMP)

    error_message = Column(Text)

    created_at = Column(TIMESTAMP)
