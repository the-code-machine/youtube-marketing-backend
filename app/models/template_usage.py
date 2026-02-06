from sqlalchemy import Column, Integer, String, TIMESTAMP
from app.core.database import Base

class TemplateUsage(Base):
    __tablename__ = "template_usage"

    id = Column(Integer, primary_key=True, index=True)

    template_id = Column(Integer)
    lead_id = Column(Integer)

    status = Column(String)
    sent_at = Column(TIMESTAMP)
