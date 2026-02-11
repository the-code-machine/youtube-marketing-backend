from pydantic import BaseModel
from typing import Optional
from datetime import datetime

# Base Schema (Shared properties)
class TemplateBase(BaseModel):
    title: str
    subject: Optional[str] = None
    body: Optional[str] = None # The HTML content
    ai_prompt_instructions: Optional[str] = None # Instructions for AI generation
    category: Optional[str] = "General"
    is_active: bool = True

# Schema for CREATING a template
class TemplateCreate(TemplateBase):
    pass

# Schema for UPDATING (all fields optional)
class TemplateUpdate(BaseModel):
    title: Optional[str] = None
    subject: Optional[str] = None
    body: Optional[str] = None
    ai_prompt_instructions: Optional[str] = None
    category: Optional[str] = None
    is_active: Optional[bool] = None

# Schema for READING (Response to Frontend)
class TemplateResponse(TemplateBase):
    id: int
    created_at: datetime
    # We might want to know how many campaigns use this template
    usage_count: Optional[int] = 0

    class Config:
        from_attributes = True