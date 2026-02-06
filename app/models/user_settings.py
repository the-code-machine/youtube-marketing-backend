from sqlalchemy import Column, Integer, String, TIMESTAMP
from app.core.database import Base

class UserSettings(Base):
    __tablename__ = "user_settings"

    user_id = Column(Integer, primary_key=True)

    timezone = Column(String, default="UTC")

    daily_email_limit = Column(Integer, default=100)
    daily_ig_limit = Column(Integer, default=50)

    preferred_ai_model = Column(String, default="gemini")
    email_provider = Column(String, default="zoho")

    created_at = Column(TIMESTAMP)
    updated_at = Column(TIMESTAMP)
