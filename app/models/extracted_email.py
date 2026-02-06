from sqlalchemy import Column, Integer, String, Text, Float, TIMESTAMP
from app.core.database import Base

class ExtractedEmail(Base):
    __tablename__ = "extracted_emails"

    id = Column(Integer, primary_key=True, index=True)

    channel_id = Column(String)

    email = Column(Text, nullable=False)
    source = Column(Text)
    confidence = Column(Float)

    status = Column(String, default="new")

    discovered_at = Column(TIMESTAMP)
    created_at = Column(TIMESTAMP)
