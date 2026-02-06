from sqlalchemy import Column, Integer, String, Boolean, TIMESTAMP, Text
from app.core.database import Base

class TargetCategory(Base):
    __tablename__ = "target_categories"

    id = Column(Integer, primary_key=True, index=True)

    name = Column(Text)
    youtube_query = Column(Text)

    parent_category = Column(String)
    language = Column(String(10))
    country_code = Column(String(5))
    last_fetched_at = Column(TIMESTAMP)

    min_subscribers = Column(Integer, default=0)
    max_subscribers = Column(Integer)

    min_video_duration = Column(Integer)
    max_video_duration = Column(Integer)

    is_active = Column(Boolean, default=True)
    priority = Column(Integer, default=1)

    created_at = Column(TIMESTAMP)
    updated_at = Column(TIMESTAMP)
