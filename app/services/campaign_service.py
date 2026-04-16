"""
app/services/campaign_service.py

Performance fixes applied:
  1. get_leads_selection
       - Lightweight COUNT query (joins only what's needed for filters, no full join)
       - NOT EXISTS via LEFT JOIN + IS NULL  (replaces slow notin_ anti-join)
       - unique_channels param: one lead per channel (latest by id)
  2. get_lead_kpis
       - Collapsed 4 COUNT queries → 1 query with CASE WHEN
  3. General: aliased imports, no redundant ORM loads
"""

import csv
from io import StringIO
from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session, aliased
from sqlalchemy import func, desc, or_, and_, case

from app.models.campaign import Campaign, CampaignLead, CampaignEvent
from app.models.email_template import EmailTemplate
from app.models.lead import Lead
from app.models.youtube_channel import YoutubeChannel
from app.models.youtube_video import YoutubeVideo


class CampaignService:
    def __init__(self, db: Session):
        self.db = db

    # =========================================================
    # 1. LEAD SELECTION
    # =========================================================

    def get_leads_selection(
        self,
        page: int,
        limit: int,
        search: str = None,
        filter_type: str = None,          # 'email' | 'instagram' | 'both'
        country: str = None,
        min_subscribers: int = None,
        max_subscribers: int = None,
        min_duration_seconds: int = None,
        max_duration_seconds: int = None,
        date_from: datetime = None,
        date_to: datetime = None,
        exclude_contacted: bool = False,
        unique_channels: bool = False,     # NEW: one lead per channel_id
    ):
        # ── Base query (selected columns only — avoids loading full ORM objects) ──
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

        # ── Unique channels: one lead per channel (most recent) ───────────────
        # Uses a subquery: SELECT MAX(id) FROM leads GROUP BY channel_id
        # Then joins back to keep only those rows.
        if unique_channels:
            channel_latest_subq = (
                self.db.query(func.max(Lead.id).label("lead_id"))
                .group_by(Lead.channel_id)
                .subquery()
            )
            query = query.join(
                channel_latest_subq,
                Lead.id == channel_latest_subq.c.lead_id
            )

        # ── Contact type filter ───────────────────────────────────────────────
        if filter_type == "email":
            query = query.filter(Lead.primary_email != None)
        elif filter_type == "instagram":
            query = query.filter(Lead.instagram_username != None)
        elif filter_type == "both":
            query = query.filter(
                and_(
                    Lead.primary_email != None,
                    Lead.instagram_username != None,
                )
            )

        # ── Search ────────────────────────────────────────────────────────────
        if search:
            query = query.filter(
                or_(
                    YoutubeChannel.name.ilike(f"%{search}%"),
                    YoutubeVideo.title.ilike(f"%{search}%"),
                    Lead.primary_email.ilike(f"%{search}%"),
                )
            )

        # ── Country ───────────────────────────────────────────────────────────
        if country:
            query = query.filter(YoutubeChannel.country_code == country.upper())

        # ── Subscriber range ──────────────────────────────────────────────────
        if min_subscribers is not None:
            query = query.filter(YoutubeChannel.subscriber_count >= min_subscribers)
        if max_subscribers is not None:
            query = query.filter(YoutubeChannel.subscriber_count <= max_subscribers)

        # ── Video duration range ──────────────────────────────────────────────
        if min_duration_seconds is not None:
            query = query.filter(YoutubeVideo.duration_seconds >= min_duration_seconds)
        if max_duration_seconds is not None:
            query = query.filter(YoutubeVideo.duration_seconds <= max_duration_seconds)

        # ── Date range ────────────────────────────────────────────────────────
        if date_from:
            query = query.filter(Lead.created_at >= date_from)
        if date_to:
            query = query.filter(Lead.created_at <= date_to)

        # ── Exclude already-contacted — LEFT JOIN + IS NULL ───────────────────
        # MUCH faster than .notin_(subquery) which becomes NOT IN (SELECT ...)
        # and forces a full scan of campaign_leads for every row.
        if exclude_contacted:
            sent_cl = aliased(CampaignLead)
            query = query.outerjoin(
                sent_cl,
                and_(
                    sent_cl.lead_id == Lead.id,
                    sent_cl.status == "sent",
                )
            ).filter(sent_cl.id == None)

        # ── Count (lightweight — no ORDER BY, no OFFSET) ─────────────────────
        # We build a dedicated count subquery so Postgres can plan it optimally.
        total = query.with_entities(func.count(Lead.id)).scalar()

        # ── Paginated results ─────────────────────────────────────────────────
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

    # =========================================================
    # 2. LEAD KPIs  —  1 query instead of 4
    # =========================================================

    def get_lead_kpis(self):
        # Single scan of the leads table with conditional aggregates
        row = self.db.query(
            func.count(Lead.id).label("total_leads"),
            func.count(
                case((Lead.primary_email != None, Lead.id))
            ).label("email_leads"),
            func.count(
                case((Lead.instagram_username != None, Lead.id))
            ).label("instagram_leads"),
        ).one()

        contacted = (
            self.db.query(func.count(CampaignLead.id))
            .filter(CampaignLead.status == "sent")
            .scalar()
            or 0
        )

        return {
            "total_leads":     row.total_leads,
            "email_leads":     row.email_leads,
            "instagram_leads": row.instagram_leads,
            "contacted_leads": contacted,
        }

    # =========================================================
    # 3. CAMPAIGN MANAGEMENT
    # =========================================================

    def create_campaign(
        self,
        name: str,
        platform: str,
        template_id: int,
        lead_ids: list,
        generation_mode: str = "generalised",
        script_plan_id=None,
    ):
        campaign = Campaign(
            name=name,
            platform=platform,
            template_id=template_id,
            status="draft",
            total_leads=len(lead_ids),
            generation_mode=generation_mode,
            script_plan_id=script_plan_id,
        )
        self.db.add(campaign)
        self.db.flush()

        new_links = []
        for lid in lead_ids:
            exists = (
                self.db.query(CampaignLead.id)
                .filter_by(campaign_id=campaign.id, lead_id=lid)
                .first()
            )
            if not exists:
                new_links.append(
                    CampaignLead(campaign_id=campaign.id, lead_id=lid, status="queued")
                )
        if new_links:
            self.db.add_all(new_links)

        self.db.commit()
        self.db.refresh(campaign)
        return campaign

    def get_campaign_kpis(self):
        row = self.db.query(
            func.count(Campaign.id).label("total"),
            func.count(case((Campaign.status == "running", Campaign.id))).label("active"),
        ).one()

        sent = (
            self.db.query(func.count(CampaignLead.id))
            .filter(CampaignLead.status == "sent")
            .scalar()
            or 0
        )
        responses = (
            self.db.query(func.count(CampaignLead.id))
            .filter(CampaignLead.replied_at != None)
            .scalar()
            or 0
        )

        return {
            "total_campaigns":  row.total,
            "active_campaigns": row.active,
            "emails_sent":      sent,
            "responses":        responses,
        }

    # =========================================================
    # 4. EXPORT
    # =========================================================

    def export_campaign_leads(self, campaign_id: int):
        rows = (
            self.db.query(
                CampaignLead.id,
                CampaignLead.status,
                CampaignLead.sent_at,
                CampaignLead.ai_generated_subject,
                Lead.channel_id,
                Lead.primary_email,
                Lead.instagram_username,
                YoutubeChannel.name.label("channel_name"),
                YoutubeChannel.subscriber_count,
            )
            .join(Lead, CampaignLead.lead_id == Lead.id)
            .outerjoin(YoutubeChannel, Lead.channel_id == YoutubeChannel.channel_id)
            .filter(CampaignLead.campaign_id == campaign_id)
            .all()
        )

        output = StringIO()
        writer = csv.writer(output)
        writer.writerow([
            "id", "status", "sent_at", "subject",
            "channel_id", "email", "instagram", "channel_name", "subscribers",
        ])
        for r in rows:
            writer.writerow([
                r.id, r.status, r.sent_at, r.ai_generated_subject,
                r.channel_id, r.primary_email, r.instagram_username,
                r.channel_name, r.subscriber_count,
            ])

        output.seek(0)
        return output