from sqlalchemy import Column, Integer, BigInteger, Float, Date, TIMESTAMP
from app.core.database import Base

class DailyStats(Base):
    __tablename__ = "daily_stats"

    stat_date = Column(Date, primary_key=True)

    channels_discovered = Column(Integer, default=0)
    videos_fetched = Column(Integer, default=0)

    emails_extracted = Column(Integer, default=0)
    emails_sent = Column(Integer, default=0)
    emails_bounced = Column(Integer, default=0)
    emails_replied = Column(Integer, default=0)

    leads_created = Column(Integer, default=0)
    leads_contacted = Column(Integer, default=0)
    leads_replied = Column(Integer, default=0)

    ig_comments_sent = Column(Integer, default=0)
    ig_dms_sent = Column(Integer, default=0)
    ig_replies_received = Column(Integer, default=0)

    jobs_run = Column(Integer, default=0)
    jobs_failed = Column(Integer, default=0)

    avg_engagement_score = Column(Float)
    avg_lead_score = Column(Float)

    ai_requests = Column(Integer, default=0)
    ai_tokens_used = Column(BigInteger, default=0)

    created_at = Column(TIMESTAMP)
    updated_at = Column(TIMESTAMP)
