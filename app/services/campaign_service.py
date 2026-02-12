import csv
from io import StringIO
from datetime import datetime
from sqlalchemy.orm import Session
from sqlalchemy import func, desc, or_

# MODELS
from app.models.campaign import Campaign, CampaignLead, CampaignEvent
from app.models.email_template import EmailTemplate
from app.models.lead import Lead
from app.models.youtube_channel import YoutubeChannel
from app.models.youtube_video import YoutubeVideo 

class CampaignService:
    def __init__(self, db: Session):
        self.db = db

    # ---------------------------------------------------------
    # 1. LEAD SELECTION (FIXED WITH JOIN)
    # ---------------------------------------------------------
    def get_leads_selection(self, page: int, limit: int, search: str = None, filter_type: str = None):
    # 1. Triple Join Query
        query = self.db.query(
        Lead.id,
        Lead.channel_id,
        Lead.video_id,
        Lead.primary_email,
        Lead.instagram_username,
        Lead.status,
        Lead.created_at,
        # Channel Columns
        YoutubeChannel.name.label("channel_name"),
        YoutubeChannel.thumbnail_url.label("channel_thumb"),
        YoutubeChannel.subscriber_count,
        # Video Columns (Joined via Lead.video_id)
        YoutubeVideo.title.label("video_title"),
        YoutubeVideo.thumbnail_url.label("video_thumb")
    ).outerjoin(
        YoutubeChannel, Lead.channel_id == YoutubeChannel.channel_id
    ).outerjoin(
        YoutubeVideo, Lead.video_id == YoutubeVideo.video_id
    )

    # 2. Filters
        if filter_type == 'email':
            query = query.filter(Lead.primary_email != None)
        elif filter_type == 'instagram':
            query = query.filter(Lead.instagram_username != None)
    
        if search:
            query = query.filter(or_(
            YoutubeChannel.name.ilike(f"%{search}%"),
            YoutubeVideo.title.ilike(f"%{search}%"),
            Lead.primary_email.ilike(f"%{search}%")
        ))

        total = query.count()
        results = query.order_by(desc(Lead.created_at)).offset((page - 1) * limit).limit(limit).all()

         # 3. Data Mapping with URL Construction
        data = []
        for r in results:
            data.append({
            "id": r.id,
            "channel_id": r.channel_id,
            "video_id": r.video_id,
            "title": r.channel_name or "Unknown",
            "thumbnail_url": r.channel_thumb,
            "channel_url": f"https://www.youtube.com/channel/{r.channel_id}",
            "subscriber_count": r.subscriber_count or 0,
            
            # Video Details
            "video_title": r.video_title,
            "video_thumbnail": r.video_thumb,
            "video_url": f"https://www.youtube.com/watch?v={r.video_id}" if r.video_id else None,
            
            "email": r.primary_email,
            "instagram": r.instagram_username,
            "status": r.status,
            "created_at": r.created_at
        })

        return {"data": data, "total": total, "page": page, "limit": limit}
    
    def get_lead_kpis(self):
        return {
            "total_leads": self.db.query(func.count(Lead.id)).scalar() or 0,
            "email_leads": self.db.query(func.count(Lead.id)).filter(Lead.primary_email != None).scalar() or 0,
            "instagram_leads": self.db.query(func.count(Lead.id)).filter(Lead.instagram_username != None).scalar() or 0,
            "contacted_leads": self.db.query(func.count(CampaignLead.id)).filter(CampaignLead.status == 'sent').scalar() or 0
        }

    # ---------------------------------------------------------
    # 2. CAMPAIGN MANAGEMENT
    # ---------------------------------------------------------
    def create_campaign(self, name: str, platform: str, template_id: int, lead_ids: list[int]):
        campaign = Campaign(
            name=name,
            platform=platform,
            template_id=template_id,
            status="draft",
            total_leads=len(lead_ids)
        )
        self.db.add(campaign)
        self.db.flush()

        # FORCE "queued" status. 
        # We don't care what the template says yet. 
        # The AI Worker will handle the text generation.
        initial_status = "queued" 

        new_links = []
        for lid in lead_ids:
            # Check duplicate to avoid crashing
            exists = self.db.query(CampaignLead).filter_by(campaign_id=campaign.id, lead_id=lid).first()
            if not exists:
                new_links.append(CampaignLead(
                    campaign_id=campaign.id,
                    lead_id=lid,
                    status=initial_status # <--- ALWAYS QUEUED
                ))
        
        if new_links:
            self.db.add_all(new_links)
        
        self.db.commit()
        self.db.refresh(campaign)
        return campaign
    
    def get_campaign_kpis(self):
        return {
            "total_campaigns": self.db.query(func.count(Campaign.id)).scalar() or 0,
            "active_campaigns": self.db.query(func.count(Campaign.id)).filter(Campaign.status == 'running').scalar() or 0,
            "emails_sent": self.db.query(func.count(CampaignLead.id)).filter(CampaignLead.status == 'sent').scalar() or 0,
            "responses": self.db.query(func.count(CampaignLead.id)).filter(CampaignLead.replied_at != None).scalar() or 0
        }

    # ---------------------------------------------------------
    # 3. EXPORT (Rich Data)
    # ---------------------------------------------------------
    def export_campaign_leads(self, campaign_id: int):
        # Join with YoutubeChannel for names in CSV
        results = self.db.query(
            YoutubeChannel.name,
            Lead.channel_id,
            Lead.primary_email,
            Lead.instagram_username,
            CampaignLead.status,
            CampaignLead.ai_generated_subject
        ).join(CampaignLead, Lead.id == CampaignLead.lead_id)\
         .outerjoin(YoutubeChannel, Lead.channel_id == YoutubeChannel.channel_id)\
         .filter(CampaignLead.campaign_id == campaign_id).all()

        output = StringIO()
        writer = csv.writer(output)
        writer.writerow(["Channel Name", "Channel ID", "Email", "Instagram", "Status", "Subject Line"])
        
        for r in results:
            name = r.name or r.channel_id
            writer.writerow([name, r.channel_id, r.primary_email, r.instagram_username, r.status, r.ai_generated_subject])
            
        output.seek(0)
        return output