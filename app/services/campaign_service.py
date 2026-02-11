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

class CampaignService:
    def __init__(self, db: Session):
        self.db = db

    # ---------------------------------------------------------
    # 1. LEAD SELECTION (FIXED WITH JOIN)
    # ---------------------------------------------------------
    def get_leads_selection(self, page: int, limit: int, search: str = None, filter_type: str = None):
        """
        Fetches Leads JOINED with YoutubeChannel to provide rich UI data.
        """
        # 1. Select Columns explicitly to avoid N+1 queries
        query = self.db.query(
            Lead.id,
            Lead.channel_id,
            Lead.primary_email,
            Lead.instagram_username,
            Lead.status,
            Lead.created_at,
            # Joined Columns
            YoutubeChannel.name,
            YoutubeChannel.thumbnail_url,
            YoutubeChannel.subscriber_count,
            YoutubeChannel.total_video_count
        ).outerjoin(
            YoutubeChannel, 
            Lead.channel_id == YoutubeChannel.channel_id
        )

        # 2. Apply Filters
        if filter_type == 'email':
            query = query.filter(Lead.primary_email != None)
        elif filter_type == 'instagram':
            query = query.filter(Lead.instagram_username != None)
        
        # 3. Apply Search (Check both Name and Email)
        if search:
            query = query.filter(or_(
                YoutubeChannel.name.ilike(f"%{search}%"),
                Lead.channel_id.ilike(f"%{search}%"),
                Lead.primary_email.ilike(f"%{search}%")
            ))

        # 4. Pagination
        total = query.count()
        results = query.order_by(desc(Lead.created_at)).offset((page - 1) * limit).limit(limit).all()

        # 5. Map to Schema
        data = []
        for r in results:
            data.append({
                "id": r.id,
                "channel_id": r.channel_id,
                # Fallback to channel_id if name is missing
                "title": r.name or r.channel_id, 
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

        # Fetch template to check if AI is needed
        # CORRECT: Pass the class directly
        template = self.db.query(EmailTemplate).get(template_id)
        # If template has AI instructions, we queue for generation. Otherwise ready.
        # (Note: Using getattr to be safe if model changed)
        has_ai = getattr(template, 'is_ai_powered', False) or getattr(template, 'ai_prompt_instructions', None)
        initial_status = "queued" if has_ai else "ready_to_send"

        new_links = []
        for lid in lead_ids:
            exists = self.db.query(CampaignLead).filter_by(campaign_id=campaign.id, lead_id=lid).first()
            if not exists:
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