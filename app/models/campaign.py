from sqlalchemy import Column, Integer, String, Text, Boolean, TIMESTAMP, ForeignKey, Float, JSON
from sqlalchemy.orm import relationship
from datetime import datetime
from app.core.database import Base


# ---------------------------------------------------------
# 2. CAMPAIGNS (The Batch)
# ---------------------------------------------------------
class Campaign(Base):
    __tablename__ = "campaigns"

    id = Column(Integer, primary_key=True, index=True)
    
    name = Column(String) # e.g. "Gaming Channel Outreach - Jan"
    status = Column(String, default="draft") # 'draft', 'scheduled', 'running', 'paused', 'completed'
    
    # Configuration
    platform = Column(String) # 'email', 'instagram'
    template_id = Column(Integer, ForeignKey("email_templates.id"))
    
    # Relationship
    email_template = relationship("EmailTemplate", back_populates="campaigns")
    leads = relationship("CampaignLead", back_populates="campaign")
    
    # Scheduling
    scheduled_start = Column(TIMESTAMP, nullable=True)
    daily_limit = Column(Integer, default=50)
    
    # Live Analytics (Aggregated)
    total_leads = Column(Integer, default=0)
    generated_count = Column(Integer, default=0) # How many have AI content ready?
    sent_count = Column(Integer, default=0)
    opened_count = Column(Integer, default=0)
    replied_count = Column(Integer, default=0)
    
    created_at = Column(TIMESTAMP, default=datetime.utcnow)
    updated_at = Column(TIMESTAMP, default=datetime.utcnow)

    # Relationships
    template = relationship("OutreachTemplate", back_populates="campaigns")
    leads = relationship("CampaignLead", back_populates="campaign")


# ---------------------------------------------------------
# 3. CAMPAIGN LEADS (The Execution Item)
# ---------------------------------------------------------
class CampaignLead(Base):
    __tablename__ = "campaign_leads"

    id = Column(Integer, primary_key=True, index=True)
    
    campaign_id = Column(Integer, ForeignKey("campaigns.id"))
    lead_id = Column(Integer, ForeignKey("leads.id"))
    
    # Status Flow: 'queued' -> 'processing_ai' -> 'ready' -> 'sending' -> 'sent' -> 'failed'
    status = Column(String, default="queued")
    
    # AI Generation Result (Unique per User)
    ai_generated_subject = Column(Text, nullable=True)
    ai_generated_body = Column(Text, nullable=True)
    
    # Metadata used for generation (Snapshot)
    # We store what video title/tags were used so we know why the AI wrote what it wrote
    context_snapshot = Column(JSON, nullable=True) 

    # Tracking IDs
    message_id = Column(String, nullable=True) # Gmail Message ID / IG Thread ID
    
    sent_at = Column(TIMESTAMP, nullable=True)
    opened_at = Column(TIMESTAMP, nullable=True)
    replied_at = Column(TIMESTAMP, nullable=True)
    
    error_message = Column(Text, nullable=True)

    # Relationships
    campaign = relationship("Campaign", back_populates="leads")
    lead = relationship("Lead") # Assumes you have a Lead model already
    events = relationship("CampaignEvent", back_populates="campaign_lead")


# ---------------------------------------------------------
# 4. CAMPAIGN EVENTS (The Tracking Log)
# ---------------------------------------------------------
class CampaignEvent(Base):
    __tablename__ = "campaign_events"

    id = Column(Integer, primary_key=True, index=True)
    
    campaign_lead_id = Column(Integer, ForeignKey("campaign_leads.id"))
    
    # Event Types: 'generated', 'sent', 'opened', 'clicked', 'replied', 'bounced'
    event_type = Column(String, nullable=False)
    
    # Extra data (e.g., which link was clicked? what was the reply snippet?)
    metadata_json = Column(JSON, nullable=True)
    
    created_at = Column(TIMESTAMP, default=datetime.utcnow)

    # Relationships
    campaign_lead = relationship("CampaignLead", back_populates="events")