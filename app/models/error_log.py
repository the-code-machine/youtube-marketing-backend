from sqlalchemy import Column, Integer, String, Text, Boolean, TIMESTAMP
from app.core.database import Base

class ErrorLog(Base):
    __tablename__ = "error_logs"

    id = Column(Integer, primary_key=True, index=True)

    service = Column(String)
    error_type = Column(String)
    error_message = Column(Text)

    stack_trace = Column(Text)

    related_job_id = Column(Integer)
    related_channel_id = Column(String)

    resolved = Column(Boolean, default=False)

    created_at = Column(TIMESTAMP)
