import csv
from io import StringIO
from datetime import datetime, timedelta
from typing import Tuple, List, Optional

from sqlalchemy.orm import Session
from sqlalchemy import func, text, desc, or_

from app.models.target_category import TargetCategory
from app.models.youtube_channel import YoutubeChannel
from app.models.channel_metrics import ChannelMetrics
from app.models.lead import Lead
from app.models.extracted_email import ExtractedEmail
from app.models.channel_social import ChannelSocialLink
from app.schemas.segment import SegmentCard, SegmentKPIs, GraphResponse, TableResponse

class SegmentService:
    def __init__(self, db: Session):
        self.db = db

    # ---------------------------------------------------------
    # 1. SEGMENT RESOLVER (Fixed to use ONLY existing fields)
    # ---------------------------------------------------------
    def _apply_segment_filter(self, query, segment_id: str, model=YoutubeChannel):
        """
        Parses the segment_id and applies the correct SQLAlchemy filter.
        Strictly uses existing DB columns.
        """
        # A. Database Categories (IDs are integers)
        if segment_id.isdigit():
            return query.filter(model.category_id == int(segment_id))

        # B. Special "Uncategorized" Segment
        if segment_id == "uncategorized":
            return query.filter(model.category_id == None)

        # C. Logic Filters (String IDs)
        
        # 1. Subscriber Filters (Field: subscriber_count exists)
        if segment_id == "filter_subs_1m":
            return query.filter(model.subscriber_count >= 1000000)
        
        if segment_id == "filter_subs_100k":
            return query.filter(model.subscriber_count.between(100000, 999999))
        
        # 2. Country Filter (Field: country_code exists)
        if segment_id.startswith("filter_country_"):
            country_code = segment_id.replace("filter_country_", "").upper()
            return query.filter(model.country_code == country_code)

        # 3. AI Suggested (Field: ai_lead_score exists on ChannelMetrics)
        # We must join ChannelMetrics if we are querying YoutubeChannel
        if segment_id == "filter_ai_suggested":
            # Only apply if we are querying the Channel model directly
            if model == YoutubeChannel:
                return query.join(
                    ChannelMetrics, 
                    YoutubeChannel.channel_id == ChannelMetrics.channel_id
                ).filter(ChannelMetrics.ai_lead_score >= 8.0) # High score threshold

        # 4. REMOVED: filter_duration_long 
        # Reason: 'avg_video_duration' column does not exist on YoutubeChannel.
        
        return query

    # ---------------------------------------------------------
    # 2. LIST SEGMENTS (Cards API)
    # ---------------------------------------------------------
    def get_all_segments(self) -> List[SegmentCard]:
        cards = []

        # 1. Fetch DB Categories (The "Scraping Targets")
        db_cats = self.db.query(TargetCategory).filter(TargetCategory.is_active == True).all()
        
        for i, cat in enumerate(db_cats):
            status = "active" if i < 4 else "passive"
            
            # Count items
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
        # Only add filters supported by _apply_segment_filter
        filters = [
            ("filter_subs_1m", "Top Creators (1M+)", "star", "Elite Tier Channels"),
            ("filter_subs_100k", "Mid-Tier (100k-1M)", "trending", "High Growth Potential"),
            ("filter_country_us", "USA Creators", "globe", "Geographic Segment"),
            ("filter_ai_suggested", "AI Suggested", "sparkles", "High Lead Score (>8.0)"),
        ]

        for fid, ftitle, ficon, fdesc in filters:
            q = self.db.query(func.count(YoutubeChannel.channel_id))
            
            # Handle the specific join logic for AI count
            if fid == "filter_ai_suggested":
                q = q.join(ChannelMetrics, YoutubeChannel.channel_id == ChannelMetrics.channel_id)
                
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
        # Base Query
        q_curr = self.db.query(func.count(model.id))
        q_prev = self.db.query(func.count(model.id))
        
        # Apply Logic for Channel-related models
        # If filtering Leads/Emails by segment, we must JOIN YoutubeChannel
        if model != YoutubeChannel:
            # Assumes Lead/Email has channel_id to link back
            if hasattr(model, 'channel_id'):
                q_curr = q_curr.join(YoutubeChannel, model.channel_id == YoutubeChannel.channel_id)
                q_prev = q_prev.join(YoutubeChannel, model.channel_id == YoutubeChannel.channel_id)
                
                # If filter is AI, join Metrics too
                if segment_id == "filter_ai_suggested":
                    q_curr = q_curr.join(ChannelMetrics, YoutubeChannel.channel_id == ChannelMetrics.channel_id)
                    q_prev = q_prev.join(ChannelMetrics, YoutubeChannel.channel_id == ChannelMetrics.channel_id)
        
        elif segment_id == "filter_ai_suggested":
             q_curr = q_curr.join(ChannelMetrics, YoutubeChannel.channel_id == ChannelMetrics.channel_id)
             q_prev = q_prev.join(ChannelMetrics, YoutubeChannel.channel_id == ChannelMetrics.channel_id)

        # Apply Time & Segment Filters
        q_curr = self._apply_segment_filter(q_curr, segment_id, YoutubeChannel)
        q_curr = q_curr.filter(model.created_at >= start, model.created_at <= end)
        
        duration = end - start
        prev_start = start - duration
        q_prev = self._apply_segment_filter(q_prev, segment_id, YoutubeChannel)
        q_prev = q_prev.filter(model.created_at >= prev_start, model.created_at < start)
        
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
            # Stub for videos (Video model doesn't have ID column in standard way usually, using count(*))
            total_videos={"current": 0, "previous": 0, "change_percent": 0, "trend": "neutral"}, 
            total_leads=self._calc_metric(Lead, segment_id, start_date, end_date),
            total_emails=self._calc_metric(ExtractedEmail, segment_id, start_date, end_date),
            total_instagram=self._calc_metric(ChannelSocialLink, segment_id, start_date, end_date),
            responses_received=self._calc_metric(Lead, segment_id, start_date, end_date)
        )

    # ---------------------------------------------------------
    # 4. SEGMENT TABLE
    # ---------------------------------------------------------
    def get_segment_table(self, segment_id: str, page: int, limit: int, search: str = None):
        offset = (page - 1) * limit
        
        # Base Query: Select Columns
        # We perform an OUTER JOIN on TargetCategory to allow 'uncategorized' or 'filter' views to work
        query = self.db.query(
            YoutubeChannel.channel_id,
            YoutubeChannel.title,
            YoutubeChannel.subscriber_count,
            YoutubeChannel.country_code,
            YoutubeChannel.updated_at,
            TargetCategory.name.label("category_name")
        ).outerjoin(TargetCategory, YoutubeChannel.category_id == TargetCategory.id)

        # Apply Search
        if search:
            query = query.filter(YoutubeChannel.title.ilike(f"%{search}%"))

        # Apply Segment Logic
        query = self._apply_segment_filter(query, segment_id, YoutubeChannel)

        # Sorting & Pagination
        total = query.count()
        results = query.order_by(desc(YoutubeChannel.subscriber_count)).offset(offset).limit(limit).all()

        # Transform
        data = []
        for r in results:
            # Fetch Lead Info for Contact Columns
            lead = self.db.query(Lead).filter(Lead.channel_id == r.channel_id).first()
            email = lead.primary_email if lead else None
            ig = lead.instagram_username if lead else None

            data.append({
                "channel_id": r.channel_id,
                "channel_name": r.title,
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
        writer.writerow(["Channel Name", "Subscribers", "Email", "Instagram", "Category", "Country"])
        
        for row in table_res.data:
            writer.writerow([
                row["channel_name"],
                row["subscribers"],
                row["email"],
                row["instagram"],
                row["category_name"],
                row["country"]
            ])
            
        output.seek(0)
        return output