from datetime import datetime
from sqlalchemy.orm import Session
from sqlalchemy import func, desc, or_
from app.models.campaign import CampaignLead, Campaign
from app.models.lead import Lead
from app.models.youtube_channel import YoutubeChannel

class AIStoreService:
    def __init__(self, db: Session):
        self.db = db

    def get_ai_history(self, page: int, limit: int, search: str = None, status: str = None):
        # 1. Base Query: CampaignLead -> Join Campaign -> Join Lead -> Outer Join YoutubeChannel
        query = self.db.query(
            CampaignLead,
            Campaign.name.label("campaign_name"),
            YoutubeChannel.name.label("channel_title"),
            YoutubeChannel.thumbnail_url,
            YoutubeChannel.subscriber_count
        ).join(
            Campaign, CampaignLead.campaign_id == Campaign.id
        ).join(
            Lead, CampaignLead.lead_id == Lead.id
        ).outerjoin(
            YoutubeChannel, Lead.channel_id == YoutubeChannel.channel_id
        )

        # 2. Filter: Only show items where AI has actually generated something
        query = query.filter(CampaignLead.ai_generated_body != None)

        # 3. Apply Filters
        if status:
            query = query.filter(CampaignLead.status == status)
        
        if search:
            query = query.filter(or_(
                YoutubeChannel.name.ilike(f"%{search}%"),
                Lead.channel_id.ilike(f"%{search}%"),
                CampaignLead.ai_generated_subject.ilike(f"%{search}%")
            ))

        # 4. Pagination
        total = query.count()
        results = query.order_by(desc(CampaignLead.id))\
                       .offset((page - 1) * limit)\
                       .limit(limit).all()

        # 5. Map results to Schema
        data = []
        for row in results:
            # row is a tuple: (CampaignLead, campaign_name, channel_title, thumbnail, subs)
            lead_item = row[0]
            
            data.append({
                "id": lead_item.id,
                "campaign_name": row.campaign_name,
                "channel_id": lead_item.lead.channel_id, # Access via relationship
                "channel_title": row.channel_title or lead_item.lead.channel_id,
                "thumbnail_url": row.thumbnail_url,
                "subscriber_count": row.subscriber_count or 0,
                "ai_subject": lead_item.ai_generated_subject,
                "ai_body": lead_item.ai_generated_body,
                "status": lead_item.status,
                # Use sent_at or fallback to creation if distinct generation time isn't tracked
                "generated_at": lead_item.sent_at or datetime.now() 
            })

        return {
            "data": data,
            "total": total,
            "page": page,
            "limit": limit
        }

    def get_kpis(self):
        # Total items with AI content
        total_gen = self.db.query(func.count(CampaignLead.id))\
            .filter(CampaignLead.ai_generated_body != None).scalar() or 0
            
        # Items waiting for review
        waiting = self.db.query(func.count(CampaignLead.id))\
            .filter(CampaignLead.status == 'review_ready').scalar() or 0
            
        # Items sent (Approved)
        sent = self.db.query(func.count(CampaignLead.id))\
            .filter(CampaignLead.status == 'sent').scalar() or 0

        # Calculate approximate word usage (simple proxy for token usage)
        # Note: Doing this in Python for simplicity, SQL sum(length) is faster but db-specific
        # For scalability, you'd want a separate 'usage_stats' table.
        # This is a lightweight estimation for MVP.
        sample_texts = self.db.query(CampaignLead.ai_generated_body)\
            .filter(CampaignLead.ai_generated_body != None).limit(1000).all()
        
        total_words = sum(len(text[0].split()) for text in sample_texts if text[0])

        return {
            "total_generated": total_gen,
            "waiting_review": waiting,
            "approved_sent": sent,
            "total_words_generated": total_words
        }