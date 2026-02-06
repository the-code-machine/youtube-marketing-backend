from sqlalchemy import Column, Integer, BigInteger, Float, Date, String, TIMESTAMP
from app.core.database import Base

class CategoryStats(Base):
    __tablename__ = "category_stats"

    stat_date = Column(Date, primary_key=True)
    category = Column(String, primary_key=True)

    channels_discovered = Column(Integer, default=0)
    videos_fetched = Column(Integer, default=0)

    emails_extracted = Column(Integer, default=0)
    emails_sent = Column(Integer, default=0)
    emails_replied = Column(Integer, default=0)

    leads_created = Column(Integer, default=0)
    leads_contacted = Column(Integer, default=0)
    leads_replied = Column(Integer, default=0)

    ig_comments_sent = Column(Integer, default=0)
    ig_dms_sent = Column(Integer, default=0)

    avg_engagement_score = Column(Float)
    avg_lead_score = Column(Float)

    subscriber_gain = Column(BigInteger)
    video_growth = Column(Integer)

    created_at = Column(TIMESTAMP)
