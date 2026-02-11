from sqlalchemy import Column, Integer, String, Text, Boolean, TIMESTAMP
from app.core.database import Base
from sqlalchemy.orm import relationship # Add this

class EmailTemplate(Base):
    __tablename__ = "email_templates"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer)
    
    title = Column(String) # Internal name (e.g. "Gaming Outreach V1")
    
    # 1. The AI Instructions (New Field)
    # If NULL, this is a standard static template.
    # If SET, this tells the AI what to write (e.g. "Write a friendly intro...")
    ai_prompt_instructions = Column(Text, nullable=True)

    # 2. The HTML Wrapper (Existing Field)
    # Stores: "<html><body> <img src='logo.png'> {{content}} </body></html>"
    body = Column(Text) 
    
    # AI generated subject fallback or static subject
    subject = Column(Text)

    category = Column(String)
    is_active = Column(Boolean, default=True)
    created_at = Column(TIMESTAMP)

    # Relationship to Campaign
    campaigns = relationship("Campaign", back_populates="email_template")