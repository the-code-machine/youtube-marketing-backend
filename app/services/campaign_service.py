import csv
from io import StringIO
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import func, desc, or_

# IMPORT YOUR EXISTING MODELS
from app.models.campaign import Campaign, CampaignLead, CampaignEvent, OutreachTemplate
from app.models.lead import Lead 
# (Assuming Lead model exists from previous context with channel_id, primary_email, etc.)

class CampaignService:
    def __init__(self, db: Session):
        self.db = db

    # ---------------------------------------------------------
    # 1. LEAD SELECTION (For "Leads View")
    # ---------------------------------------------------------
    def get_leads_selection(self, page: int, limit: int, search: str = None, filter_type: str = None):
        """
        Fetch leads for the frontend selection table.
        """
        query = self.db.query(Lead)

        # Filters
        if filter_type == 'email':
            query = query.filter(Lead.primary_email != None)
        elif filter_type == 'instagram':
            query = query.filter(Lead.instagram_username != None)
        
        # Search
        if search:
            query = query.filter(or_(
                Lead.channel_id.ilike(f"%{search}%"),
                Lead.primary_email.ilike(f"%{search}%")
            ))

        total = query.count()
        leads = query.order_by(desc(Lead.created_at)).offset((page - 1) * limit).limit(limit).all()

        return {
            "data": leads,
            "total": total,
            "page": page,
            "limit": limit
        }

    def get_lead_kpis(self):
        """
        Stats for the top of the Leads page.
        """
        return {
            "total_leads": self.db.query(func.count(Lead.id)).scalar() or 0,
            "email_leads": self.db.query(func.count(Lead.id)).filter(Lead.primary_email != None).scalar() or 0,
            "instagram_leads": self.db.query(func.count(Lead.id)).filter(Lead.instagram_username != None).scalar() or 0,
            # 'Contacted' logic assumes they are in a campaign
            "contacted_leads": self.db.query(func.count(CampaignLead.id)).filter(CampaignLead.status == 'sent').scalar() or 0
        }

    # ---------------------------------------------------------
    # 2. CAMPAIGN MANAGEMENT
    # ---------------------------------------------------------
    def create_campaign(self, name: str, platform: str, template_id: int, lead_ids: list[int]):
        """
        Creates a campaign and links the selected leads.
        """
        # 1. Create Campaign
        campaign = Campaign(
            name=name,
            platform=platform,
            template_id=template_id,
            status="draft",
            total_leads=len(lead_ids)
        )
        self.db.add(campaign)
        self.db.flush() # Get ID

        # 2. Bulk Link Leads
        # Check template to see if we need AI
        template = self.db.query(OutreachTemplate).get(template_id)
        initial_status = "queued" if template.is_ai_powered else "ready_to_send"

        new_links = []
        for lid in lead_ids:
            # Check duplicate
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
        """
        Stats for the Campaign Dashboard.
        """
        return {
            "total_campaigns": self.db.query(func.count(Campaign.id)).scalar() or 0,
            "active_campaigns": self.db.query(func.count(Campaign.id)).filter(Campaign.status == 'running').scalar() or 0,
            "emails_sent": self.db.query(func.count(CampaignLead.id)).filter(CampaignLead.status == 'sent').scalar() or 0,
            "responses": self.db.query(func.count(CampaignLead.id)).filter(CampaignLead.replied_at != None).scalar() or 0
        }

    # ---------------------------------------------------------
    # 3. EXPORT
    # ---------------------------------------------------------
    def export_campaign_leads(self, campaign_id: int):
        """
        Generates CSV for manual Instagram outreach or backup.
        """
        results = self.db.query(
            Lead.channel_id, 
            Lead.primary_email, 
            Lead.instagram_username, 
            CampaignLead.status
        ).join(CampaignLead, Lead.id == CampaignLead.lead_id)\
         .filter(CampaignLead.campaign_id == campaign_id).all()

        output = StringIO()
        writer = csv.writer(output)
        writer.writerow(["Channel Name", "Email", "Instagram", "Status"])
        
        for r in results:
            writer.writerow([r.channel_id, r.primary_email, r.instagram_username, r.status])
            
        output.seek(0)
        return output