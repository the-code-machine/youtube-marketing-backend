from sqlalchemy import Column, Integer, String, Text, TIMESTAMP
from app.core.database import Base

class InstagramAction(Base):
    __tablename__ = "instagram_actions"

    id = Column(Integer, primary_key=True, index=True)

    channel_id = Column(String)
    instagram_username = Column(Text)

    action_type = Column(String)
    action_text = Column(Text)

    status = Column(String)

    platform_post_url = Column(Text)

    executed_at = Column(TIMESTAMP)
    created_at = Column(TIMESTAMP)
