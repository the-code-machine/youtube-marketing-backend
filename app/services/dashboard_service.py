from sqlalchemy.orm import Session
from sqlalchemy import func, text
from datetime import datetime, timedelta
from app.models.channel_social import ChannelSocialLink
from app.models.extracted_email import ExtractedEmail
from app.models.youtube_channel import YoutubeChannel
from app.models.lead import Lead
from app.models.campaign import CampaignEvent
from app.models.email_message import EmailMessage
from app.models.youtube_video import YoutubeVideo

class DashboardService:
    def __init__(self, db: Session):
        self.db = db
    
    def _pk(self, model):
        if model == YoutubeChannel:
            return model.channel_id
        if model == YoutubeVideo:
            return model.video_id
        return model.id


    def _get_date_range(self, range_key: str):
        now = datetime.utcnow()
        if range_key == "24h":
            return now - timedelta(hours=24), now, "hour"
        elif range_key == "7d":
            return now - timedelta(days=7), now, "day"
        elif range_key == "30d":
            return now - timedelta(days=30), now, "day"
        return now - timedelta(days=7), now, "day" # Default

    def _calculate_growth(self, current: int, previous: int):
        if previous == 0:
            return 100.0 if current > 0 else 0.0
        return round(((current - previous) / previous) * 100, 1)
    
    def _get_sparkline(self, model, days=7):
        end = datetime.utcnow()
        start = end - timedelta(days=days)

        pk = self._pk(model)

        rows = self.db.query(
        func.date_trunc('day', model.created_at).label("day"),
        func.count(pk)
    ).filter(
        model.created_at >= start
    ).group_by(text("day")).order_by(text("day")).all()

        return [
        {
            "timestamp": r.day,
            "label": r.day.strftime("%b %d"),
            "value": r[1]
        } for r in rows
    ]
    

    def get_kpi_graphs(self, view_mode: str):
        """
        Returns a dictionary where keys are metric names and values are the graph data.
        """
        graphs = {}

        # 1. DATA VIEW GRAPHS
        if view_mode in ["DATA", "COMBINED"]:
            graphs["channelsOverTime"] = self._get_sparkline(YoutubeChannel)
            graphs["videosOverTime"] = self._get_sparkline(YoutubeVideo)
            graphs["emailsOverTime"] = self._get_sparkline(ExtractedEmail)
            graphs["socialsOverTime"] = self._get_sparkline(ChannelSocialLink)
            graphs["leadsOverTime"] = self._get_sparkline(Lead)


        # 2. LEAD VIEW GRAPHS
        if view_mode in ["LEAD", "COMBINED"]:
            graphs["leadsOverTime"] = self._get_sparkline(Lead)
            
            # For 'Emails Sent', we query the Events table
            # We filter specifically for 'sent_email' events
            sent_results = self.db.query(
                func.date_trunc('day', CampaignEvent.created_at).label("day"),
                func.count(CampaignEvent.id)
            ).filter(
                CampaignEvent.event_type == 'sent_email',
                CampaignEvent.created_at >= datetime.utcnow() - timedelta(days=7)
            ).group_by(text("day")).order_by(text("day")).all()
            
            graphs["emailsSentOverTime"] = [
                {"timestamp": r.day, "label": r.day.strftime("%b %d"), "value": r[1]} 
                for r in sent_results
            ]

        return graphs
    
    def _get_metric(self, model, start, end):
        """Generic helper to count records in a time range"""
        pk = self._pk(model)

        # Current Period
        curr = self.db.query(func.count(pk)).filter(
            model.created_at >= start, 
            model.created_at <= end
        ).scalar() or 0
        
        # Previous Period (Same duration back)
        duration = end - start
        prev_start = start - duration
        prev = self.db.query(func.count(pk)).filter(
            model.created_at >= prev_start, 
            model.created_at < start
        ).scalar() or 0
        
        return {
            "value": curr,
            "previous_value": prev,
            "percentage_change": self._calculate_growth(curr, prev),
            "trend": "up" if curr >= prev else "down"
        }

    def get_kpis(self, view_mode: str, date_range: str):
        start, end, _ = self._get_date_range(date_range)
        
        data = {}
        
        # 1. DATA VIEW METRICS
        if view_mode in ["DATA", "COMBINED"]:
            data["total_channels"] = self._get_metric(YoutubeChannel, start, end)
            data["total_videos"] = self._get_metric(YoutubeVideo, start, end)

            data["total_emails"] = self._get_metric(ExtractedEmail, start, end)
            data["total_socials"] = self._get_metric(ChannelSocialLink, start, end)

        # 2. LEAD VIEW METRICS
        if view_mode in ["LEAD", "COMBINED"]:
            data["total_leads"] = self._get_metric(Lead, start, end)
            # Emails Sent (From CampaignEvents)
            data["emails_sent"] = self._get_metric(CampaignEvent, start, end)
            data["instagram_dms"] = {"value": 0, "previous_value": 0, "percentage_change": 0, "trend": "neutral"}
            data["responses_received"] = {"value": 0, "previous_value": 0, "percentage_change": 0, "trend": "neutral"}

        return {"view_mode": view_mode, "data": data}

    def get_main_graph(self, view_mode: str, date_range: str):
        start, end, granularity = self._get_date_range(date_range)
        
        # Decide which table to query based on view
        if view_mode == "DATA":
            model = YoutubeChannel
            label = "New Channels"
        elif view_mode == "LEAD":
            model = Lead
            label = "Leads Generated"
        else:
            # Combined logic (Complex: requires joining or two queries)
            model = Lead 
            label = "Combined Activity"

        # PGSQL Date Truncation
        trunc_type = 'hour' if granularity == 'hour' else 'day'
        pk = self._pk(model)

        results = self.db.query(
            func.date_trunc(trunc_type, model.created_at).label("time_bucket"),
            func.count(pk)
        ).filter(
            model.created_at >= start
        ).group_by(text("time_bucket")).order_by(text("time_bucket")).all()

        formatted = []
        for r in results:
            formatted.append({
                "timestamp": r.time_bucket,
                "label": r.time_bucket.strftime("%H:%M" if granularity == 'hour' else "%b %d"),
                "value": r[1],
                "category": label
            })
            
        return {
            "view_mode": view_mode,
            "granularity": granularity,
            "series": formatted
        }