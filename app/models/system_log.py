from sqlalchemy import Column, Integer, String, Text, TIMESTAMP
from app.core.database import Base

class SystemLog(Base):
    __tablename__ = "system_logs"

    id = Column(Integer, primary_key=True, index=True)

    service = Column(String)
    level = Column(String)

    message = Column(Text)

    related_job_id = Column(Integer)
    related_channel_id = Column(String)

    created_at = Column(TIMESTAMP)
