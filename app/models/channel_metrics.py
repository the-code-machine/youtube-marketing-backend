from sqlalchemy import Column, String, Integer, BigInteger, Float, TIMESTAMP
from app.core.database import Base

class ChannelMetrics(Base):
    __tablename__ = "channel_metrics"

    channel_id = Column(String, primary_key=True)

    avg_views = Column(BigInteger)
    avg_likes = Column(BigInteger)
    avg_comments = Column(BigInteger)

    engagement_rate = Column(Float)

    subscriber_gain_7d = Column(BigInteger)
    subscriber_gain_30d = Column(BigInteger)

    video_count_7d = Column(Integer)
    video_count_30d = Column(Integer)

    reply_rate = Column(Float)

    last_video_at = Column(TIMESTAMP)

    ai_lead_score = Column(Float)

    updated_at = Column(TIMESTAMP)
