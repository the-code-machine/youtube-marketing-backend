from sqlalchemy.orm import Session
from sqlalchemy import func, text
from datetime import datetime, timedelta
from app.models.youtube_channel import YoutubeChannel
from app.models.lead import Lead
from app.models.campaign import CampaignEvent
from app.models.email_message import EmailMessage

class DashboardService:
    def __init__(self, db: Session):
        self.db = db

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

    # ... inside DashboardService class ...

    def _get_sparkline(self, model, days=7):
        """
        Fetches a simplified daily count for the last N days.
        Used for the mini-graphs on KPI cards.
        """
        end_date = datetime.utcnow()
        start_date = end_date - timedelta(days=days)
        
        # Query: Group by Day, Count IDs
        results = self.db.query(
            func.date_trunc('day', model.created_at).label("day"),
            func.count(model.id)
        ).filter(
            model.created_at >= start_date
        ).group_by(text("day")).order_by(text("day")).all()

        # Format for Frontend (Recharts)
        data_points = []
        for r in results:
            data_points.append({
                "timestamp": r.day,
                "label": r.day.strftime("%b %d"), # e.g. "Feb 10"
                "value": r[1]
            })
            
        return data_points

    def get_kpi_graphs(self, view_mode: str):
        """
        Returns a dictionary where keys are metric names and values are the graph data.
        """
        graphs = {}

        # 1. DATA VIEW GRAPHS
        if view_mode in ["DATA", "COMBINED"]:
            graphs["channelsOverTime"] = self._get_sparkline(YoutubeChannel)
            graphs["emailsOverTime"] = self._get_sparkline(EmailMessage)
            
            # For 'Videos', if you have a Video model
            # graphs["videosOverTime"] = self._get_sparkline(YoutubeVideo) 
            
            # For 'Socials', we usually count Leads with social links
            graphs["socialsOverTime"] = self._get_sparkline(Lead) 

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
        # Current Period
        curr = self.db.query(func.count(model.id)).filter(
            model.created_at >= start, 
            model.created_at <= end
        ).scalar() or 0
        
        # Previous Period (Same duration back)
        duration = end - start
        prev_start = start - duration
        prev = self.db.query(func.count(model.id)).filter(
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
            data["total_videos"] = {"value": 0, "previous_value": 0, "percentage_change": 0, "trend": "neutral"} # Stub if Video model heavy
            data["total_emails"] = self._get_metric(ExtractedEmail, start, end)
            # Instagram count (Logic: Channels where instagram_username is not null)
            # This requires a custom query, simplified here for brevity
            data["total_instagram"] = self._get_metric(Lead, start, end) 
            data["total_socials"] = self._get_metric(Lead, start, end)

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
        
        results = self.db.query(
            func.date_trunc(trunc_type, model.created_at).label("time_bucket"),
            func.count(model.id)
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