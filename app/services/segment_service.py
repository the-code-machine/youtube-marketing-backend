import csv
from io import StringIO
from datetime import datetime, timedelta
from typing import Tuple, List

from sqlalchemy.orm import Session
from sqlalchemy import func, text, desc, or_

from app.models.target_category import TargetCategory
from app.models.youtube_channel import YoutubeChannel
from app.models.lead import Lead
from app.models.extracted_email import ExtractedEmail
from app.models.channel_social import ChannelSocialLink
from app.schemas.segment import SegmentCard, SegmentKPIs, GraphResponse, TableResponse

class SegmentService:
    def __init__(self, db: Session):
        self.db = db

    # ---------------------------------------------------------
    # 1. SEGMENT RESOLVER (The Core Logic)
    # ---------------------------------------------------------
    def _apply_segment_filter(self, query, segment_id: str, model=YoutubeChannel):
        """
        Parses the segment_id and applies the correct SQLAlchemy filter.
        """
        # A. Database Categories (IDs are integers, passed as strings)
        if segment_id.isdigit():
            # Assuming YoutubeChannel has a 'category_id' or we join via string name
            # For this implementation, we assume we filter by category relationship
            return query.filter(model.category_id == int(segment_id))

        # B. Logic Filters (String IDs)
        if segment_id == "filter_subs_1m":
            return query.filter(model.subscriber_count >= 1000000)
        
        if segment_id == "filter_subs_100k":
            return query.filter(model.subscriber_count.between(100000, 999999))
        
        if segment_id == "filter_duration_long":
            # Assuming 'avg_duration' column exists on Channel or calculated from videos
            return query.filter(model.avg_video_duration > 600) # > 10 mins

        if segment_id.startswith("filter_country_"):
            country_code = segment_id.replace("filter_country_", "").upper()
            return query.filter(model.country_code == country_code)

        if segment_id == "filter_ai_suggested":
             # Placeholder for AI logic column
            return query.filter(model.is_ai_recommended == True)

        return query

    # ---------------------------------------------------------
    # 2. LIST SEGMENTS (Cards API)
    # ---------------------------------------------------------
    def get_all_segments(self) -> List[SegmentCard]:
        cards = []

        # 1. Fetch DB Categories (The "Scraping Targets")
        db_cats = self.db.query(TargetCategory).filter(TargetCategory.is_active == True).all()
        
        for i, cat in enumerate(db_cats):
            # First 4 are "Active Fetching", rest are "Queued" or "Passive"
            status = "active" if i < 4 else "passive"
            
            # Count items (simplified)
            count = self.db.query(func.count(YoutubeChannel.channel_id))\
                .filter(YoutubeChannel.category_id == cat.id).scalar() or 0

            cards.append(SegmentCard(
                id=str(cat.id),
                title=cat.name,
                type="youtube_category",
                description=f"Targeting: {cat.youtube_query}",
                icon="youtube", # Mapped on frontend
                status=status,
                total_items=count
            ))

        # 2. Add Logic Filters (Hardcoded Business Logic)
        filters = [
            ("filter_subs_1m", "Top Creators (1M+)", "star", "Elite Tier Channels"),
            ("filter_subs_100k", "Mid-Tier (100k-1M)", "trending", "High Growth Potential"),
            ("filter_country_us", "USA Creators", "globe", "Geographic Segment"),
            ("filter_duration_long", "Long Form (>10m)", "clock", "Deep Dive Content"),
        ]

        for fid, ftitle, ficon, fdesc in filters:
            # Quick count for filters
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
    # 3. SEGMENT KPIS
    # ---------------------------------------------------------
    def _calc_metric(self, model, segment_id, start, end):
        # Current
        q_curr = self.db.query(func.count(model.id)).filter(model.created_at >= start, model.created_at <= end)
        if model == YoutubeChannel:
            q_curr = self._apply_segment_filter(q_curr, segment_id, model)
        # Note: applying segment filter to Lead/Email models requires joins. 
        # Simplified: We assume Leads link to Channels.
        
        curr = q_curr.scalar() or 0
        
        # Previous
        duration = end - start
        prev_start = start - duration
        q_prev = self.db.query(func.count(model.id)).filter(model.created_at >= prev_start, model.created_at < start)
        if model == YoutubeChannel:
             q_prev = self._apply_segment_filter(q_prev, segment_id, model)
             
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
        # Note: In a real app, Leads/Emails would need to JOIN with YoutubeChannel 
        # to respect the 'segment_id' filter. 
        # For this example, we focus on Channel metrics which are direct.
        
        return SegmentKPIs(
            total_channels=self._calc_metric(YoutubeChannel, segment_id, start_date, end_date),
            total_videos=self._calc_metric(YoutubeChannel, segment_id, start_date, end_date), # Stub for Video model
            total_leads=self._calc_metric(Lead, segment_id, start_date, end_date),
            total_emails=self._calc_metric(ExtractedEmail, segment_id, start_date, end_date),
            total_instagram=self._calc_metric(ChannelSocialLink, segment_id, start_date, end_date),
            responses_received=self._calc_metric(Lead, segment_id, start_date, end_date) # Stub
        )

    # ---------------------------------------------------------
    # 4. SEGMENT TABLE (Paginated)
    # ---------------------------------------------------------
    def get_segment_table(self, segment_id: str, page: int, limit: int, search: str = None):
        offset = (page - 1) * limit
        
        # Base Query
        query = self.db.query(
            YoutubeChannel.channel_id,
            YoutubeChannel.title,
            YoutubeChannel.subscriber_count,
            YoutubeChannel.country_code,
            YoutubeChannel.updated_at,
            TargetCategory.name.label("category_name")
        ).join(TargetCategory, YoutubeChannel.category_id == TargetCategory.id)

        # Apply Segment Logic
        query = self._apply_segment_filter(query, segment_id, YoutubeChannel)

        # Apply Search
        if search:
            query = query.filter(YoutubeChannel.title.ilike(f"%{search}%"))

        # Sorting & Pagination
        total = query.count()
        results = query.order_by(desc(YoutubeChannel.subscriber_count)).offset(offset).limit(limit).all()

        # Transform to Response
        data = []
        for r in results:
            # Fetch Lead Info (N+1 optimization would be needed here in prod)
            lead = self.db.query(Lead).filter(Lead.channel_id == r.channel_id).first()
            email = lead.primary_email if lead else None
            ig = lead.instagram_username if lead else None

            data.append({
                "channel_id": r.channel_id,
                "channel_name": r.title,
                "subscribers": r.subscriber_count,
                "country": r.country_code,
                "category_name": r.category_name,
                "email": email,
                "instagram": ig,
                "fetched_at": r.updated_at
            })

        return TableResponse(page=page, limit=limit, total=total, data=data)

    # ---------------------------------------------------------
    # 5. CSV EXPORT
    # ---------------------------------------------------------
    def export_segment_csv(self, segment_id: str):
        # Re-use logic from table but without pagination limit
        # In prod, use streaming response for large datasets
        table_res = self.get_segment_table(segment_id, 1, 10000) 
        
        output = StringIO()
        writer = csv.writer(output)
        
        # Headers
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