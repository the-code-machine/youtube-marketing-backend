from sqlalchemy import Column, Integer, String, Float, BigInteger, Text, TIMESTAMP
from app.core.database import Base

class AIUsageLog(Base):
    __tablename__ = "ai_usage_logs"

    id = Column(Integer, primary_key=True, index=True)

    task_type = Column(String)
    model_name = Column(String)

    input_tokens = Column(Integer, default=0)
    output_tokens = Column(Integer, default=0)
    total_tokens = Column(Integer, default=0)

    estimated_cost = Column(Float)

    related_channel_id = Column(String)
    related_video_id = Column(String)

    status = Column(String, default="success")

    created_at = Column(TIMESTAMP)
