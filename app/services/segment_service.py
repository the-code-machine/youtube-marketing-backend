import csv
from io import StringIO
from datetime import datetime, timedelta
from typing import Tuple, List, Optional, Dict

from sqlalchemy.orm import Session
from sqlalchemy import func, text, desc, or_, and_

# Models
from app.models.target_category import TargetCategory
from app.models.youtube_channel import YoutubeChannel
from app.models.youtube_video import YoutubeVideo
from app.models.lead import Lead
from app.models.extracted_email import ExtractedEmail
from app.models.channel_social import ChannelSocialLink
from app.models.channel_metrics import ChannelMetrics
from app.schemas.segment import SegmentCard, SegmentKPIs, GraphResponse, TableResponse

class SegmentService:
    def __init__(self, db: Session):
        self.db = db

    # ---------------------------------------------------------
    # HELPER: Get Primary Key Dynamically
    # ---------------------------------------------------------
    def _get_pk(self, model):
        if model == YoutubeChannel:
            return model.channel_id
        if model == YoutubeVideo:
            return model.video_id
        if model == ChannelMetrics:
            return model.channel_id
        return model.id

    # ---------------------------------------------------------
    # 1. SEGMENT RESOLVER (Smart Filters)
    # ---------------------------------------------------------
    def _apply_segment_filter(self, query, segment_id: str, model=YoutubeChannel):
        """
        Applies filtering logic based on the Segment ID.
        """
        # A. Database Categories
        if segment_id.isdigit():
            if hasattr(model, 'category_id'):
                return query.filter(model.category_id == int(segment_id))
            return query 

        # B. Special "Uncategorized"
        if segment_id == "uncategorized":
            return query.filter(model.category_id == None)

        # C. Logic Filters
        if segment_id == "filter_subs_1m":
            return query.filter(model.subscriber_count >= 1000000)
        
        if segment_id == "filter_subs_100k":
            return query.filter(model.subscriber_count.between(100000, 999999))
        
        if segment_id.startswith("filter_country_"):
            code = segment_id.replace("filter_country_", "").upper()
            return query.filter(model.country_code == code)

        # Engagement Score
        if segment_id == "filter_high_engagement":
            return query.filter(model.engagement_score >= 2.0)

        # Has Email
        if segment_id == "filter_has_email":
            return query.filter(model.has_email == True)

        # Verified Leads
        if segment_id == "filter_top_leads":
            return query.filter(model.lead_score >= 8.0)

        return query

    # ---------------------------------------------------------
    # 2. LIST SEGMENTS (Cards API)
    # ---------------------------------------------------------
    def get_all_segments(self) -> List[SegmentCard]:
        cards = []

        # 1. Database Categories
        db_cats = self.db.query(TargetCategory).filter(TargetCategory.is_active == True).all()
        for i, cat in enumerate(db_cats):
            count = self.db.query(func.count(YoutubeChannel.channel_id))\
                .filter(YoutubeChannel.category_id == cat.id).scalar() or 0

            cards.append(SegmentCard(
                id=str(cat.id),
                title=cat.name,
                type="youtube_category",
                description=f"Targeting: {cat.youtube_query}",
                icon="youtube", 
                status="active" if i < 4 else "passive",
                total_items=count
            ))

        # 2. Smart Filters
        filters = [
            ("filter_subs_1m", "Top Creators (1M+)", "star", "Channels with massive reach."),
            ("filter_subs_100k", "Mid-Tier (100k-1M)", "trending", "High growth potential."),
            ("filter_high_engagement", "High Engagement", "activity", "Engagement Score > 2.0"),
            ("filter_has_email", "Has Email", "mail", "Ready for outreach."),
            ("filter_top_leads", "Verified Leads", "check", "AI Lead Score > 8.0"),
            ("filter_country_us", "USA Creators", "globe", "Region: United States"),
        ]

        for fid, ftitle, ficon, fdesc in filters:
            q = self.db.query(func.count(YoutubeChannel.channel_id))
            count = self._apply_segment_filter(q, fid, YoutubeChannel).scalar() or 0
            
            cards.append(SegmentCard(
                id=fid,
                title=ftitle,
                type="filter",
                description=fdesc,
                icon=ficon,
                status="active",
                total_items=count
            ))

        return cards

    # ---------------------------------------------------------
    # 3. SEGMENT KPIS (FIXED)
    # ---------------------------------------------------------
    def _calc_metric(self, model, segment_id, start, end):
        # FIX: Use helper to get correct PK (video_id vs channel_id vs id)
        pk = self._get_pk(model)
        
        q_curr = self.db.query(func.count(pk))
        q_prev = self.db.query(func.count(pk))
        
        # Join if needed
        if model != YoutubeChannel:
            # Assumes model has channel_id (Lead, Video, Email all do)
            if hasattr(model, 'channel_id'):
                q_curr = q_curr.join(YoutubeChannel, model.channel_id == YoutubeChannel.channel_id)
                q_prev = q_prev.join(YoutubeChannel, model.channel_id == YoutubeChannel.channel_id)
        
        # Apply Segment Filter
        q_curr = self._apply_segment_filter(q_curr, segment_id, YoutubeChannel)
        q_prev = self._apply_segment_filter(q_prev, segment_id, YoutubeChannel)

        # Date Filter
        q_curr = q_curr.filter(model.created_at >= start, model.created_at <= end)
        
        duration = end - start
        prev_start = start - duration
        q_prev = q_prev.filter(model.created_at >= prev_start, model.created_at < start)
        
        curr = q_curr.scalar() or 0
        prev = q_prev.scalar() or 0
        
        pct = 0.0
        if prev > 0:
            pct = round(((curr - prev) / prev) * 100, 1)
        
        return {"current": curr, "previous": prev, "change_percent": pct, "trend": "up" if curr >= prev else "down"}

    def get_segment_kpis(self, segment_id: str, start_date: datetime, end_date: datetime):
        return SegmentKPIs(
            total_channels=self._calc_metric(YoutubeChannel, segment_id, start_date, end_date),
            # This line caused the crash before, now fixed by _get_pk
            total_videos=self._calc_metric(YoutubeVideo, segment_id, start_date, end_date),
            total_leads=self._calc_metric(Lead, segment_id, start_date, end_date),
            total_emails=self._calc_metric(ExtractedEmail, segment_id, start_date, end_date),
            total_instagram=self._calc_metric(ChannelSocialLink, segment_id, start_date, end_date),
            responses_received=self._calc_metric(Lead, segment_id, start_date, end_date)
        )

    # ---------------------------------------------------------
    # 4. SEGMENT GRAPHS
    # ---------------------------------------------------------
    def get_segment_graphs(self, segment_id: str, start: datetime, end: datetime, granularity: str = "daily"):
        trunc_type = 'hour' if granularity == 'hourly' else 'day'
        
        def get_series(model, label):
            # FIX: Use helper here too
            pk = self._get_pk(model)
            
            query = self.db.query(
                func.date_trunc(trunc_type, model.created_at).label("bucket"),
                func.count(pk)
            ).filter(model.created_at >= start)
            
            if model != YoutubeChannel:
                query = query.join(YoutubeChannel, model.channel_id == YoutubeChannel.channel_id)
            
            query = self._apply_segment_filter(query, segment_id, YoutubeChannel)
            results = query.group_by(text("bucket")).order_by(text("bucket")).all()
            
            return {
                "name": label,
                "data": [{"x": r.bucket.isoformat(), "y": r[1]} for r in results]
            }

        return GraphResponse(
            granularity=granularity,
            series=[
                get_series(YoutubeChannel, "Channels Discovered"),
                get_series(Lead, "Leads Generated")
            ]
        )

    # ---------------------------------------------------------
    # 5. SEGMENT TABLE
    # ---------------------------------------------------------
    def get_segment_table(self, segment_id: str, page: int, limit: int, search: str = None):
        offset = (page - 1) * limit
        
        query = self.db.query(
            YoutubeChannel.channel_id,
            YoutubeChannel.name,
            YoutubeChannel.thumbnail_url,
            YoutubeChannel.subscriber_count,
            YoutubeChannel.total_video_count,
            YoutubeChannel.total_view_count,
            YoutubeChannel.engagement_score,
            YoutubeChannel.country_code,
            YoutubeChannel.created_at.label("fetched_at"),
            YoutubeChannel.primary_email,
            YoutubeChannel.primary_instagram,
            TargetCategory.name.label("category_name")
        ).outerjoin(TargetCategory, YoutubeChannel.category_id == TargetCategory.id)

        if search:
            # Search by name or channel_id
            query = query.filter(
                or_(
                    YoutubeChannel.name.ilike(f"%{search}%"),
                    YoutubeChannel.channel_id.ilike(f"%{search}%")
                )
            )

        query = self._apply_segment_filter(query, segment_id, YoutubeChannel)

        total = query.count()
        results = query.order_by(desc(YoutubeChannel.subscriber_count)).offset(offset).limit(limit).all()

        data = []
        for r in results:
            data.append({
                "channel_id": r.channel_id,
                "name": r.name,
                "thumbnail_url": r.thumbnail_url,
                "subscribers": r.subscriber_count or 0,
                "video_count": r.total_video_count or 0,
                "view_count": r.total_view_count or 0,
                "engagement_score": r.engagement_score,
                "email": r.primary_email,
                "instagram": r.primary_instagram,
                "country": r.country_code,
                "category_name": r.category_name or "Uncategorized",
                "fetched_at": r.fetched_at
            })

        return TableResponse(page=page, limit=limit, total=total, data=data)

    # ---------------------------------------------------------
    # 6. EXPORT
    # ---------------------------------------------------------
    def export_segment_csv(self, segment_id: str):
        res = self.get_segment_table(segment_id, 1, 5000)
        
        output = StringIO()
        writer = csv.writer(output)
        writer.writerow(["Channel Name", "Subscribers", "Videos", "Views", "Engagement", "Email", "Instagram", "Category", "Country"])
        
        for row in res.data:
            writer.writerow([
                row.name,
                row.subscribers,
                row.video_count,
                row.view_count,
                row.engagement_score,
                row.email,
                row.instagram,
                row.category_name,
                row.country
            ])
            
        output.seek(0)
        return output