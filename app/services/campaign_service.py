import csv
from io import StringIO
from datetime import datetime
from typing import Optional
from sqlalchemy.orm import Session
from sqlalchemy import func, desc, or_, and_

from app.models.campaign import Campaign, CampaignLead, CampaignEvent
from app.models.email_template import EmailTemplate
from app.models.lead import Lead
from app.models.youtube_channel import YoutubeChannel
from app.models.youtube_video import YoutubeVideo


class CampaignService:
    def __init__(self, db: Session):
        self.db = db

    # ---------------------------------------------------------
    # 1. LEAD SELECTION
    # ---------------------------------------------------------
    def get_leads_selection(
        self,
        page: int,
        limit: int,
        search: str = None,
        filter_type: str = None,       # 'email' | 'instagram' | 'both'
        country: str = None,
        min_subscribers: int = None,
        max_subscribers: int = None,
        min_duration_seconds: int = None,
        max_duration_seconds: int = None,
        date_from: datetime = None,
        date_to: datetime = None,
        exclude_contacted: bool = False,
    ):
        query = self.db.query(
            Lead.id,
            Lead.channel_id,
            Lead.video_id,
            Lead.primary_email,
            Lead.instagram_username,
            Lead.status,
            Lead.created_at,
            YoutubeChannel.name.label("channel_name"),
            YoutubeChannel.thumbnail_url.label("channel_thumb"),
            YoutubeChannel.subscriber_count,
            YoutubeChannel.country_code,
            YoutubeVideo.title.label("video_title"),
            YoutubeVideo.thumbnail_url.label("video_thumb"),
            YoutubeVideo.duration_seconds,
        ).outerjoin(
            YoutubeChannel, Lead.channel_id == YoutubeChannel.channel_id
        ).outerjoin(
            YoutubeVideo, Lead.video_id == YoutubeVideo.video_id
        )

        # ── Contact type filter ────────────────────────────────────────────────
        if filter_type == "email":
            # Has email (instagram presence doesn't matter)
            query = query.filter(Lead.primary_email != None)
        elif filter_type == "instagram":
            # Has instagram (email presence doesn't matter)
            query = query.filter(Lead.instagram_username != None)
        elif filter_type == "both":
            # Must have BOTH email AND instagram
            query = query.filter(
                and_(
                    Lead.primary_email != None,
                    Lead.instagram_username != None,
                )
            )

        # ── Search ───────────────────────────────────────────────────────────
        if search:
            query = query.filter(or_(
                YoutubeChannel.name.ilike(f"%{search}%"),
                YoutubeVideo.title.ilike(f"%{search}%"),
                Lead.primary_email.ilike(f"%{search}%"),
            ))

        # ── Country ──────────────────────────────────────────────────────────
        if country:
            query = query.filter(YoutubeChannel.country_code == country.upper())

        # ── Subscriber range ─────────────────────────────────────────────────
        if min_subscribers is not None:
            query = query.filter(YoutubeChannel.subscriber_count >= min_subscribers)
        if max_subscribers is not None:
            query = query.filter(YoutubeChannel.subscriber_count <= max_subscribers)

        # ── Video duration range ─────────────────────────────────────────────
        if min_duration_seconds is not None:
            query = query.filter(YoutubeVideo.duration_seconds >= min_duration_seconds)
        if max_duration_seconds is not None:
            query = query.filter(YoutubeVideo.duration_seconds <= max_duration_seconds)

        # ── Date range (latest leads) ────────────────────────────────────────
        if date_from:
            query = query.filter(Lead.created_at >= date_from)
        if date_to:
            query = query.filter(Lead.created_at <= date_to)

        # ── Exclude already-contacted (anti-duplicate) ───────────────────────
        if exclude_contacted:
            already_sent = (
                self.db.query(CampaignLead.lead_id)
                .filter(CampaignLead.status == "sent")
                .subquery()
            )
            query = query.filter(Lead.id.notin_(already_sent))

        total = query.count()
        results = (
            query.order_by(desc(Lead.created_at))
            .offset((page - 1) * limit)
            .limit(limit)
            .all()
        )

        data = []
        for r in results:
            data.append({
                "id":               r.id,
                "channel_id":       r.channel_id,
                "video_id":         r.video_id,
                "title":            r.channel_name or "Unknown",
                "thumbnail_url":    r.channel_thumb,
                "channel_url":      f"https://www.youtube.com/channel/{r.channel_id}",
                "subscriber_count": r.subscriber_count or 0,
                "country_code":     r.country_code,
                "video_title":      r.video_title,
                "video_thumbnail":  r.video_thumb,
                "video_url":        f"https://www.youtube.com/watch?v={r.video_id}" if r.video_id else None,
                "duration_seconds": r.duration_seconds,
                "email":            r.primary_email,
                "instagram":        r.instagram_username,
                "status":           r.status,
                "created_at":       r.created_at,
            })

        return {"data": data, "total": total, "page": page, "limit": limit}

    def get_lead_kpis(self):
        return {
            "total_leads":     self.db.query(func.count(Lead.id)).scalar() or 0,
            "email_leads":     self.db.query(func.count(Lead.id)).filter(Lead.primary_email != None).scalar() or 0,
            "instagram_leads": self.db.query(func.count(Lead.id)).filter(Lead.instagram_username != None).scalar() or 0,
            "contacted_leads": self.db.query(func.count(CampaignLead.id)).filter(CampaignLead.status == "sent").scalar() or 0,
        }

    # ---------------------------------------------------------
    # 2. CAMPAIGN MANAGEMENT
    # ---------------------------------------------------------
    def create_campaign(self, name: str, platform: str, template_id: int, lead_ids: list[int],generation_mode="generalised", script_plan_id=None):
        campaign = Campaign(
            name=name,
            platform=platform,
            template_id=template_id,
            status="draft",
            total_leads=len(lead_ids),
            generation_mode=generation_mode, script_plan_id=script_plan_id
        )
        self.db.add(campaign)
        self.db.flush()

        new_links = []
        for lid in lead_ids:
            exists = self.db.query(CampaignLead).filter_by(campaign_id=campaign.id, lead_id=lid).first()
            if not exists:
                new_links.append(CampaignLead(
                    campaign_id=campaign.id,
                    lead_id=lid,
                    status="queued",
                ))
        if new_links:
            self.db.add_all(new_links)

        self.db.commit()
        self.db.refresh(campaign)
        return campaign

    def get_campaign_kpis(self):
        return {
            "total_campaigns":  self.db.query(func.count(Campaign.id)).scalar() or 0,
            "active_campaigns": self.db.query(func.count(Campaign.id)).filter(Campaign.status == "running").scalar() or 0,
            "emails_sent":      self.db.query(func.count(CampaignLead.id)).filter(CampaignLead.status == "sent").scalar() or 0,
            "responses":        self.db.query(func.count(CampaignLead.id)).filter(CampaignLead.replied_at != None).scalar() or 0,
        }

    # ---------------------------------------------------------
    # 3. EXPORT
    # ---------------------------------------------------------
    def export_campaign_leads(self, campaign_id: int):
        results = (
            self.db.query(
                YoutubeChannel.name,
                YoutubeVideo.title,
                Lead.channel_id,
                Lead.video_id,
                Lead.primary_email,
                Lead.instagram_username,
                CampaignLead.status,
                CampaignLead.ai_generated_subject,
            )
            .join(CampaignLead, Lead.id == CampaignLead.lead_id)
            .outerjoin(YoutubeChannel, Lead.channel_id == YoutubeChannel.channel_id)
            .outerjoin(YoutubeVideo, Lead.video_id == YoutubeVideo.video_id)
            .filter(CampaignLead.campaign_id == campaign_id)
            .all()
        )

        output = StringIO()
        writer = csv.writer(output)
        writer.writerow([
            "Channel Name", "Video Title", "Channel URL",
            "Video URL", "Email", "Instagram", "Status", "Subject Line",
        ])
        for r in results:
            writer.writerow([
                r.name or r.channel_id,
                r.title,
                f"https://youtube.com/channel/{r.channel_id}",
                f"https://youtube.com/watch?v={r.video_id}" if r.video_id else "",
                r.primary_email,
                r.instagram_username,
                r.status,
                r.ai_generated_subject,
            ])

        output.seek(0)
        return output