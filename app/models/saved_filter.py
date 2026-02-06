from sqlalchemy import Column, Integer, Text, TIMESTAMP
from app.core.database import Base

class SavedFilter(Base):
    __tablename__ = "saved_filters"

    id = Column(Integer, primary_key=True, index=True)

    user_id = Column(Integer)

    name = Column(Text)
    filter_json = Column(Text)

    created_at = Column(TIMESTAMP)
