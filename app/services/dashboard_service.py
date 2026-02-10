from sqlalchemy.orm import Session
from sqlalchemy import func, text, case
from datetime import datetime, timedelta
from typing import List

# Import all your specific models
from app.models.country_stats import CountryStats
from app.models.youtube_channel import YoutubeChannel
from app.models.youtube_video import YoutubeVideo
from app.models.extracted_email import ExtractedEmail
from app.models.channel_social import ChannelSocialLink
from app.models.lead import Lead
from app.models.campaign import CampaignEvent
from app.models.instagram_action import InstagramAction
from app.models.email_message import EmailMessage

class DashboardService:
    def __init__(self, db: Session):
        self.db = db
    
    # Helper to resolve Primary Key dynamically
    def _pk(self, model):
        if model == YoutubeChannel:
            return model.channel_id
        if model == YoutubeVideo:
            return model.video_id
        if model == CountryStats: # Composite PK, use one
             return model.country_code
        return model.id

    def _get_date_range(self, range_key: str):
        now = datetime.utcnow()
        if range_key == "24h":
            return now - timedelta(hours=24), now, "hour"
        elif range_key == "7d":
            return now - timedelta(days=7), now, "day"
        elif range_key == "10d":
             return now - timedelta(days=10), now, "day"
        elif range_key == "30d":
            return now - timedelta(days=30), now, "day"
        return now - timedelta(days=7), now, "day"

    def _calculate_growth(self, current: int, previous: int):
        if previous == 0:
            return 100.0 if current > 0 else 0.0
        return round(((current - previous) / previous) * 100, 1)
    
    # --- METRIC CALCULATORS ---

    def _get_metric(self, model, start, end, filter_condition=None):
        """Generic helper to count records in a time range with optional filter"""
        pk = self._pk(model)
        
        # Build base queries
        curr_q = self.db.query(func.count(pk)).filter(model.created_at >= start, model.created_at <= end)
        
        # Previous period calculation
        duration = end - start
        prev_start = start - duration
        prev_q = self.db.query(func.count(pk)).filter(model.created_at >= prev_start, model.created_at < start)

        # Apply optional filters (e.g., platform='instagram')
        if filter_condition is not None:
            curr_q = curr_q.filter(filter_condition)
            prev_q = prev_q.filter(filter_condition)

        curr = curr_q.scalar() or 0
        prev = prev_q.scalar() or 0
        
        return {
            "value": curr,
            "previous_value": prev,
            "percentage_change": self._calculate_growth(curr, prev),
            "trend": "up" if curr >= prev else "down"
        }

    def _get_response_metric(self, start, end):
        """Specific helper for Lead Responses (checking nullable timestamp)"""
        # Current
        curr = self.db.query(func.count(Lead.id)).filter(
            Lead.reply_received_at >= start, 
            Lead.reply_received_at <= end
        ).scalar() or 0
        
        # Previous
        duration = end - start
        prev_start = start - duration
        prev = self.db.query(func.count(Lead.id)).filter(
            Lead.reply_received_at >= prev_start, 
            Lead.reply_received_at < start
        ).scalar() or 0

        return {
            "value": curr,
            "previous_value": prev,
            "percentage_change": self._calculate_growth(curr, prev),
            "trend": "up" if curr >= prev else "down"
        }

    # --- MAIN LOGIC ---

    def get_kpis(self, view_mode: str, date_range: str):
        start, end, _ = self._get_date_range(date_range)
        data = {}
        
        # 1. DATA VIEW
        if view_mode in ["DATA", "COMBINED"]:
            data["total_channels"] = self._get_metric(YoutubeChannel, start, end)
            data["total_videos"] = self._get_metric(YoutubeVideo, start, end)
            data["total_emails"] = self._get_metric(ExtractedEmail, start, end)
            data["total_socials"] = self._get_metric(ChannelSocialLink, start, end)
            
            # Instagram specific filter
            data["total_instagram"] = self._get_metric(
                ChannelSocialLink, start, end, 
                filter_condition=(ChannelSocialLink.platform == 'instagram')
            )

        # 2. LEAD VIEW
        if view_mode in ["LEAD", "COMBINED"]:
            data["total_leads"] = self._get_metric(Lead, start, end)
            
            # Emails Sent (Using CampaignEvent for accuracy of 'sent' action)
            data["emails_sent"] = self._get_metric(
                CampaignEvent, start, end,
                filter_condition=(CampaignEvent.event_type == 'sent_email')
            )
            
            # Instagram DMs (Using InstagramAction)
            data["instagram_dms"] = self._get_metric(
                InstagramAction, start, end,
                filter_condition=(InstagramAction.action_type.in_(['dm', 'message']))
            )
            
            # Responses (Using Lead.reply_received_at)
            data["responses_received"] = self._get_response_metric(start, end)

        return {"view_mode": view_mode, "data": data}

    def _get_time_series_data(self, model, start, granularity, label_name, filter_condition=None):
        trunc_type = 'hour' if granularity == 'hour' else 'day'
        pk = self._pk(model)
        
        query = self.db.query(
            func.date_trunc(trunc_type, model.created_at).label("time_bucket"),
            func.count(pk)
        ).filter(model.created_at >= start)

        if filter_condition is not None:
            query = query.filter(filter_condition)

        results = query.group_by(text("time_bucket")).order_by(text("time_bucket")).all()

        formatted = []
        for r in results:
            formatted.append({
                "timestamp": r.time_bucket,
                "label": r.time_bucket.strftime("%H:%M" if granularity == 'hour' else "%b %d"),
                "value": r[1],
                "category": label_name
            })
        return formatted

    def _get_daily_counts(self, model, start, filter_condition=None, date_col=None):
        """
        Helper: Returns a dict { '2026-02-10': count } for a specific metric
        """
        col = date_col if date_col is not None else model.created_at
        pk = self._pk(model)
        
        query = self.db.query(
            func.date_trunc('day', col).label("day"),
            func.count(pk)
        ).filter(col >= start)

        if filter_condition is not None:
            query = query.filter(filter_condition)

        results = query.group_by(text("day")).order_by(text("day")).all()
        
        # Convert to Dict for easy merging: { "2026-02-10": 55 }
        return {r.day.strftime("%Y-%m-%d"): r[1] for r in results}

    def get_main_graph(self, view_mode: str, date_range: str):
        start, end, granularity = self._get_date_range(date_range)
        
        # 1. Generate Master Timeline (All days in range)
        # We need this to ensure every day exists, even if counts are 0
        timeline = []
        current = start
        while current <= end:
            timeline.append(current.strftime("%Y-%m-%d"))
            current += timedelta(days=1)

        # 2. Fetch Individual Datasets based on View
        datasets = {}

        if view_mode in ["DATA", "COMBINED"]:
            datasets["Channels"] = self._get_daily_counts(YoutubeChannel, start)
            datasets["Videos"] = self._get_daily_counts(YoutubeVideo, start)
            datasets["Emails"] = self._get_daily_counts(ExtractedEmail, start)
            datasets["Socials"] = self._get_daily_counts(ChannelSocialLink, start)

        if view_mode in ["LEAD", "COMBINED"]:
            datasets["Leads"] = self._get_daily_counts(Lead, start)
            datasets["Emails Sent"] = self._get_daily_counts(
                CampaignEvent, start, filter_condition=(CampaignEvent.event_type == 'sent_email')
            )
            datasets["IG DMs"] = self._get_daily_counts(
                InstagramAction, start, filter_condition=(InstagramAction.action_type == 'dm')
            )
            # For Responses, use reply_received_at
            datasets["Responses"] = self._get_daily_counts(Lead, start, date_col=Lead.reply_received_at)

        # 3. Merge into Final Series
        series = []
        for day_str in timeline:
            row = {
                "timestamp": day_str,
                "label": datetime.strptime(day_str, "%Y-%m-%d").strftime("%b %d")
            }
            # Inject values for this day (default to 0)
            for metric_name, data_dict in datasets.items():
                row[metric_name] = data_dict.get(day_str, 0)
            
            series.append(row)

        return {
            "view_mode": view_mode,
            "granularity": granularity,
            "series": series # Now returns [{timestamp, label, Channels: 5, Videos: 10...}]
        }
    
    
    def _get_sparkline(self, model, days=7, filter_condition=None):
        end = datetime.utcnow()
        start = end - timedelta(days=days)
        pk = self._pk(model)

        query = self.db.query(
            func.date_trunc('day', model.created_at).label("day"),
            func.count(pk)
        ).filter(model.created_at >= start)

        if filter_condition is not None:
            query = query.filter(filter_condition)

        rows = query.group_by(text("day")).order_by(text("day")).all()

        return [
            {
                "timestamp": r.day,
                "label": r.day.strftime("%b %d"),
                "value": r[1]
            } for r in rows
        ]

    def get_kpi_graphs(self, view_mode: str):
        graphs = {}

        if view_mode in ["DATA", "COMBINED"]:
            graphs["channelsOverTime"] = self._get_sparkline(YoutubeChannel)
            graphs["videosOverTime"] = self._get_sparkline(YoutubeVideo)
            graphs["emailsOverTime"] = self._get_sparkline(ExtractedEmail)
            graphs["socialsOverTime"] = self._get_sparkline(ChannelSocialLink)
            
            # Instagram Sparkline
            graphs["instagramOverTime"] = self._get_sparkline(
                ChannelSocialLink, 
                filter_condition=(ChannelSocialLink.platform == 'instagram')
            )

        if view_mode in ["LEAD", "COMBINED"]:
            graphs["leadsOverTime"] = self._get_sparkline(Lead)
            
            graphs["emailsSentOverTime"] = self._get_sparkline(
                CampaignEvent, 
                filter_condition=(CampaignEvent.event_type == 'sent_email')
            )
            
            graphs["dmsOverTime"] = self._get_sparkline(
                InstagramAction
            )
            
            # For Responses, we need a special query because it uses reply_received_at
            end = datetime.utcnow()
            start = end - timedelta(days=7)
            resp_rows = self.db.query(
                func.date_trunc('day', Lead.reply_received_at).label("day"),
                func.count(Lead.id)
            ).filter(
                Lead.reply_received_at >= start
            ).group_by(text("day")).order_by(text("day")).all()
            
            graphs["responsesOverTime"] = [
                {"timestamp": r.day, "label": r.day.strftime("%b %d"), "value": r[1]} for r in resp_rows
            ]

        return graphs