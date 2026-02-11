import csv
from io import StringIO
from datetime import datetime
from sqlalchemy.orm import Session
from sqlalchemy import func, desc, or_

# MODELS
from app.models.campaign import Campaign, CampaignLead
from app.models.lead import Lead
from app.models.youtube_channel import YoutubeChannel 
# ^ Ensure YoutubeChannel is imported to allow the JOIN

class CampaignService:
    def __init__(self, db: Session):
        self.db = db

    # ---------------------------------------------------------
    # 1. LEAD SELECTION (Enriched with Channel Data)
    # ---------------------------------------------------------
    def get_leads_selection(self, page: int, limit: int, search: str = None, filter_type: str = None):
        """
        Fetches Leads joined with YoutubeChannel data for the frontend table.
        """
        # 1. Build Query with JOIN
        # We select specific columns to avoid over-fetching
        query = self.db.query(
            Lead.id,
            Lead.channel_id,
            Lead.primary_email,
            Lead.instagram_username,
            Lead.status,
            Lead.created_at,
            # Joined Columns from YoutubeChannel
            YoutubeChannel.name.label("title"),
            YoutubeChannel.thumbnail_url,
            YoutubeChannel.subscriber_count,
            YoutubeChannel.total_video_count
        ).join(
            YoutubeChannel, 
            Lead.channel_id == YoutubeChannel.channel_id
        )

        # 2. Filters
        if filter_type == 'email':
            query = query.filter(Lead.primary_email != None)
        elif filter_type == 'instagram':
            query = query.filter(Lead.instagram_username != None)
        
        # 3. Search (Search by Channel Name or Email)
        if search:
            query = query.filter(or_(
                YoutubeChannel.name.ilike(f"%{search}%"),
                Lead.primary_email.ilike(f"%{search}%")
            ))

        # 4. Pagination & Execution
        total = query.count()
        results = query.order_by(desc(Lead.created_at)).offset((page - 1) * limit).limit(limit).all()

        # 5. Format Data
        data = []
        for r in results:
            data.append({
                "id": r.id,
                "channel_id": r.channel_id,
                "title": r.name or r.channel_id, # Fallback to ID if name missing
                "thumbnail_url": r.thumbnail_url,
                "subscriber_count": r.subscriber_count or 0,
                "video_count": r.total_video_count or 0,
                "email": r.primary_email,
                "instagram": r.instagram_username,
                "status": r.status,
                "created_at": r.created_at
            })

        return {
            "data": data,
            "total": total,
            "page": page,
            "limit": limit
        }

    def get_lead_kpis(self):
        return {
            "total_leads": self.db.query(func.count(Lead.id)).scalar() or 0,
            "email_leads": self.db.query(func.count(Lead.id)).filter(Lead.primary_email != None).scalar() or 0,
            "instagram_leads": self.db.query(func.count(Lead.id)).filter(Lead.instagram_username != None).scalar() or 0,
            "contacted_leads": self.db.query(func.count(CampaignLead.id)).filter(CampaignLead.status == 'sent').scalar() or 0
        }

    # ---------------------------------------------------------
    # 2. CAMPAIGN OPERATIONS
    # ---------------------------------------------------------
    def create_campaign(self, name: str, platform: str, template_id: int, lead_ids: list[int]):
        # Create Campaign Entry
        campaign = Campaign(
            name=name,
            platform=platform,
            template_id=template_id,
            status="draft",
            total_leads=len(lead_ids)
        )
        self.db.add(campaign)
        self.db.flush()

        # Bulk Create Links
        # We fetch the template to check AI status once, not in loop
        # (Assuming template check handled by caller or simple query here)
        # For efficiency, we default to 'queued' if platform is email generally
        initial_status = "queued" 

        new_links = []
        for lid in lead_ids:
            # Simple deduplication check could happen here if needed
            new_links.append(CampaignLead(
                campaign_id=campaign.id,
                lead_id=lid,
                status=initial_status
            ))
        
        if new_links:
            self.db.add_all(new_links)
        
        self.db.commit()
        return campaign

    def get_campaign_kpis(self):
        return {
            "total_campaigns": self.db.query(func.count(Campaign.id)).scalar() or 0,
            "active_campaigns": self.db.query(func.count(Campaign.id)).filter(Campaign.status == 'running').scalar() or 0,
            # Note: Ensure CampaignLead model has 'sent' status logic working
            "emails_sent": self.db.query(func.count(CampaignLead.id)).filter(CampaignLead.status == 'sent').scalar() or 0,
            "responses": self.db.query(func.count(CampaignLead.id)).filter(CampaignLead.replied_at != None).scalar() or 0
        }

    def export_campaign_leads(self, campaign_id: int):
        # Detailed Export with Channel Names
        results = self.db.query(
            YoutubeChannel.name,
            Lead.primary_email,
            Lead.instagram_username,
            CampaignLead.status,
            CampaignLead.ai_generated_subject
        ).join(CampaignLead, Lead.id == CampaignLead.lead_id)\
         .join(YoutubeChannel, Lead.channel_id == YoutubeChannel.channel_id)\
         .filter(CampaignLead.campaign_id == campaign_id).all()

        output = StringIO()
        writer = csv.writer(output)
        writer.writerow(["Channel Name", "Email", "Instagram", "Status", "Subject Line"])
        
        for r in results:
            writer.writerow([r.name, r.primary_email, r.instagram_username, r.status, r.ai_generated_subject])
            
        output.seek(0)
        return output