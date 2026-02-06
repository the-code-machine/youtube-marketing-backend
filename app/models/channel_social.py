from sqlalchemy import Column, Integer, String, Text, Boolean, TIMESTAMP
from app.core.database import Base

class ChannelSocialLink(Base):
    __tablename__ = "channel_social_links"

    id = Column(Integer, primary_key=True, index=True)

    channel_id = Column(String)

    platform = Column(String)
    url = Column(Text)
    username = Column(Text)

    is_primary = Column(Boolean, default=False)

    discovered_at = Column(TIMESTAMP)
    created_at = Column(TIMESTAMP)
