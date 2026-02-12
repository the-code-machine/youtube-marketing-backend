from sqlalchemy import Column, Integer, String, Text, TIMESTAMP
from app.core.database import Base

class Lead(Base):
    __tablename__ = "leads"

    id = Column(Integer, primary_key=True, index=True)

    channel_id = Column(String)
    video_id = Column(String, unique=True)

    primary_email = Column(Text)
    instagram_username = Column(Text)

    status = Column(String, default="new")

    last_contacted_at = Column(TIMESTAMP)
    reply_received_at = Column(TIMESTAMP)

    notes = Column(Text)

    created_at = Column(TIMESTAMP)
    updated_at = Column(TIMESTAMP)
