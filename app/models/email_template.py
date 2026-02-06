from sqlalchemy import Column, Integer, String, Text, Boolean, TIMESTAMP
from app.core.database import Base

class EmailTemplate(Base):
    __tablename__ = "email_templates"

    id = Column(Integer, primary_key=True, index=True)

    user_id = Column(Integer)

    title = Column(String)
    subject = Column(Text)
    body = Column(Text)

    category = Column(String)

    is_active = Column(Boolean, default=True)

    created_at = Column(TIMESTAMP)
