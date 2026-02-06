from sqlalchemy import Column, Integer, Text, TIMESTAMP
from app.core.database import Base

class SavedView(Base):
    __tablename__ = "saved_views"

    id = Column(Integer, primary_key=True, index=True)

    user_id = Column(Integer)

    name = Column(Text)
    layout_json = Column(Text)

    created_at = Column(TIMESTAMP)
