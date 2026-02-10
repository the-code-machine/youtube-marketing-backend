import csv
from io import StringIO
from datetime import datetime, timedelta
from typing import Tuple, List, Optional

from sqlalchemy.orm import Session
from sqlalchemy import func, text, desc, or_

# Use strictly the models provided
from app.models.target_category import TargetCategory
from app.models.youtube_channel import YoutubeChannel
from app.models.youtube_video import YoutubeVideo
from app.models.channel_metrics import ChannelMetrics
from app.models.lead import Lead
from app.models.extracted_email import ExtractedEmail
from app.models.channel_social import ChannelSocialLink
from app.schemas.segment import SegmentCard, SegmentKPIs, GraphResponse, TableResponse

class SegmentService:
    def __init__(self, db: Session):
        self.db = db

    # ---------------------------------------------------------
    # HELPER: Dynamic Primary Key Resolution
    # ---------------------------------------------------------
    def _pk(self, model):
        """
        Returns the correct Primary Key column for the given model.
        Fixes the 'no attribute id' error for YoutubeChannel.
        """
        if model == YoutubeChannel:
            return model.channel_id
        if model == YoutubeVideo:
            return model.video_id
        if model == ChannelMetrics:
            return model.channel_id
        # Fallback for Lead, ExtractedEmail, etc which have 'id'
        return model.id

    # ---------------------------------------------------------
    # 1. SEGMENT RESOLVER
    # ---------------------------------------------------------
    def _apply_segment_filter(self, query, segment_id: str, model=YoutubeChannel):
        """
        Parses the segment_id and applies the correct SQLAlchemy filter.
        Strictly uses existing DB columns.
        """
        # A. Database Categories (IDs are integers)
        if segment_id.isdigit():
            # Ensure YoutubeChannel has category_id (added in previous step)
            if hasattr(model, 'category_id'):
                return query.filter(model.category_id == int(segment_id))
            return query # Fallback if column missing

        # B. Logic Filters
        
        # 1. Subscriber Filters
        if segment_id == "filter_subs_1m":
            return query.filter(model.subscriber_count >= 1000000)
        
        if segment_id == "filter_subs_100k":
            return query.filter(model.subscriber_count.between(100000, 999999))
        
        # 2. Country Filter
        if segment_id.startswith("filter_country_"):
            country_code = segment_id.replace("filter_country_", "").upper()
            return query.filter(model.country_code == country_code)

        # 3. AI Suggested (Uses ChannelMetrics)
        if segment_id == "filter_ai_suggested":
            if model == YoutubeChannel:
                # We perform the join here. The caller should NOT join manually.
                return query.join(
                    ChannelMetrics, 
                    YoutubeChannel.channel_id == ChannelMetrics.channel_id
                ).filter(ChannelMetrics.ai_lead_score >= 8.0)

        return query

    # ---------------------------------------------------------
    # 2. LIST SEGMENTS (Cards API)
    # ---------------------------------------------------------
    def get_all_segments(self) -> List[SegmentCard]:
        cards = []

        # 1. Fetch DB Categories
        db_cats = self.db.query(TargetCategory).filter(TargetCategory.is_active == True).all()
        
        for i, cat in enumerate(db_cats):
            status = "active" if i < 4 else "passive"
            
            # Use channel_id for counting
            count = self.db.query(func.count(YoutubeChannel.channel_id))\
                .filter(YoutubeChannel.category_id == cat.id).scalar() or 0

            cards.append(SegmentCard(
                id=str(cat.id),
                title=cat.name,
                type="youtube_category",
                description=f"Targeting: {cat.youtube_query}",
                icon="youtube",
                status=status,
                total_items=count
            ))

        # 2. Add Logic Filters 
        filters = [
            ("filter_subs_1m", "Top Creators (1M+)", "star", "Elite Tier Channels"),
            ("filter_subs_100k", "Mid-Tier (100k-1M)", "trending", "High Growth Potential"),
            ("filter_country_us", "USA Creators", "globe", "Geographic Segment"),
            ("filter_ai_suggested", "AI Suggested", "sparkles", "High Lead Score (>8.0)"),
        ]

        for fid, ftitle, ficon, fdesc in filters:
            # Clean query, purely on YoutubeChannel
            q = self.db.query(func.count(YoutubeChannel.channel_id))
            
            # _apply_segment_filter handles the join internally for 'ai_suggested'
            # We do NOT join ChannelMetrics here to avoid DuplicateAlias error
            
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
    # 3. SEGMENT KPIS
    # ---------------------------------------------------------
    def _calc_metric(self, model, segment_id, start, end):
        # 1. Resolve Primary Key dynamically
        pk = self._pk(model)

        # 2. Base Queries
        q_curr = self.db.query(func.count(pk))
        q_prev = self.db.query(func.count(pk))
        
        # 3. Link back to YoutubeChannel if we are filtering a child model
        if model != YoutubeChannel:
            if hasattr(model, 'channel_id'):
                q_curr = q_curr.join(YoutubeChannel, model.channel_id == YoutubeChannel.channel_id)
                q_prev = q_prev.join(YoutubeChannel, model.channel_id == YoutubeChannel.channel_id)
        
        # 4. Apply Segment Filters (Subscribers, Country, AI, etc)
        q_curr = self._apply_segment_filter(q_curr, segment_id, YoutubeChannel)
        q_prev = self._apply_segment_filter(q_prev, segment_id, YoutubeChannel)

        # 5. Apply Date Filters
        q_curr = q_curr.filter(model.created_at >= start, model.created_at <= end)
        
        duration = end - start
        prev_start = start - duration
        q_prev = q_prev.filter(model.created_at >= prev_start, model.created_at < start)
        
        # 6. Execute
        curr = q_curr.scalar() or 0
        prev = q_prev.scalar() or 0
        
        pct = 0.0
        if prev > 0:
            pct = round(((curr - prev) / prev) * 100, 1)
        
        return {
            "current": curr,
            "previous": prev,
            "change_percent": pct,
            "trend": "up" if curr >= prev else "down"
        }

    def get_segment_kpis(self, segment_id: str, start_date: datetime, end_date: datetime):
        return SegmentKPIs(
            total_channels=self._calc_metric(YoutubeChannel, segment_id, start_date, end_date),
            total_videos=self._calc_metric(YoutubeVideo, segment_id, start_date, end_date),
            total_leads=self._calc_metric(Lead, segment_id, start_date, end_date),
            total_emails=self._calc_metric(ExtractedEmail, segment_id, start_date, end_date),
            total_instagram=self._calc_metric(ChannelSocialLink, segment_id, start_date, end_date),
            responses_received=self._calc_metric(Lead, segment_id, start_date, end_date) # Stub metric, usually distinct
        )

    # ---------------------------------------------------------
    # 4. SEGMENT TABLE
    # ---------------------------------------------------------
    def get_segment_table(self, segment_id: str, page: int, limit: int, search: str = None):
        offset = (page - 1) * limit
        
        # Select Columns - REMOVED 'title' because it crashed. 
        # Using 'channel_id' as name fallback.
        query = self.db.query(
            YoutubeChannel.channel_id,
            # YoutubeChannel.title, <--- REMOVED CAUSING CRASH
            YoutubeChannel.subscriber_count,
            YoutubeChannel.country_code,
            YoutubeChannel.updated_at,
            TargetCategory.name.label("category_name")
        ).outerjoin(TargetCategory, YoutubeChannel.category_id == TargetCategory.id)

        # Apply Search (on ID since title is gone, or skip)
        if search:
            query = query.filter(YoutubeChannel.channel_id.ilike(f"%{search}%"))

        # Apply Segment Logic
        query = self._apply_segment_filter(query, segment_id, YoutubeChannel)

        # Execute
        total = query.count()
        results = query.order_by(desc(YoutubeChannel.subscriber_count)).offset(offset).limit(limit).all()

        data = []
        for r in results:
            # Fetch Lead Info
            lead = self.db.query(Lead).filter(Lead.channel_id == r.channel_id).first()
            email = lead.primary_email if lead else None
            ig = lead.instagram_username if lead else None

            data.append({
                "channel_id": r.channel_id,
                # Fallback: Use ID as name since title column is missing
                "channel_name": r.channel_id, 
                "subscribers": r.subscriber_count,
                "country": r.country_code,
                "category_name": r.category_name or "Uncategorized",
                "email": email,
                "instagram": ig,
                "fetched_at": r.updated_at
            })

        return TableResponse(page=page, limit=limit, total=total, data=data)

    # ---------------------------------------------------------
    # 5. EXPORT
    # ---------------------------------------------------------
    def export_segment_csv(self, segment_id: str):
        table_res = self.get_segment_table(segment_id, 1, 10000) 
        
        output = StringIO()
        writer = csv.writer(output)
        writer.writerow(["Channel ID", "Subscribers", "Email", "Instagram", "Category", "Country"])
        
        for row in table_res.data:
            writer.writerow([
                row["channel_name"], # This is ID now
                row["subscribers"],
                row["email"],
                row["instagram"],
                row["category_name"],
                row["country"]
            ])
            
        output.seek(0)
        return output