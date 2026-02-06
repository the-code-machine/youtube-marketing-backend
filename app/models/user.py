from sqlalchemy import Column, Integer, String, Boolean, TIMESTAMP
from app.core.database import Base

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)

    email = Column(String, unique=True, index=True)
    password_hash = Column(String)

    full_name = Column(String)

    role = Column(String, default="user")
    plan = Column(String, default="free")

    is_active = Column(Boolean, default=True)

    created_at = Column(TIMESTAMP)
    last_login = Column(TIMESTAMP)
