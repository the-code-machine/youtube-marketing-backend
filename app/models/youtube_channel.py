from sqlalchemy import Column, String, Text, Boolean, BigInteger, Integer, Float, TIMESTAMP
from app.core.database import Base

class YoutubeChannel(Base):
    __tablename__ = "youtube_channels"

    channel_id = Column(String, primary_key=True, index=True)

    name = Column(Text, nullable=False)
    handle = Column(Text)
    description = Column(Text)

    thumbnail_url = Column(Text)
    banner_url = Column(Text)

    country_code = Column(String(5))
    country_name = Column(Text)
    currency_code = Column(String(5))

    subscriber_count = Column(BigInteger)
    total_video_count = Column(Integer)
    total_view_count = Column(BigInteger)

    channel_created_at = Column(TIMESTAMP)
    last_video_published_at = Column(TIMESTAMP)

    primary_email = Column(Text)
    primary_instagram = Column(Text)
    primary_website = Column(Text)

    discovery_source = Column(Text)
    discovered_at = Column(TIMESTAMP)

    has_email = Column(Boolean, default=False)
    has_instagram = Column(Boolean, default=False)
    contacted = Column(Boolean, default=False)

    engagement_score = Column(Float)
    lead_score = Column(Float)

    is_active = Column(Boolean, default=True)
    created_at = Column(TIMESTAMP)
    updated_at = Column(TIMESTAMP)
