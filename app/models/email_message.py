from sqlalchemy import Column, Integer, String, Text, TIMESTAMP
from app.core.database import Base

class EmailMessage(Base):
    __tablename__ = "email_messages"

    id = Column(Integer, primary_key=True, index=True)

    lead_id = Column(Integer)

    email = Column(Text)
    subject = Column(Text)
    body = Column(Text)

    status = Column(String)
    provider = Column(String)

    sent_at = Column(TIMESTAMP)
    opened_at = Column(TIMESTAMP)
    replied_at = Column(TIMESTAMP)

    created_at = Column(TIMESTAMP)
