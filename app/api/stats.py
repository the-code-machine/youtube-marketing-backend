from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import date, timedelta
from app.core.database import SessionLocal
from app.models import DailyStats, YoutubeChannel, Lead, ExtractedEmail

router = APIRouter(prefix="/stats", tags=["Analytics"])

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# ---------------------------------------------------------
# 1. DASHBOARD HEADER TOTALS (Fast Count)
# ---------------------------------------------------------
@router.get("/overview")
def get_overview(db: Session = Depends(get_db)):
    """
    Returns the big numbers for the top of the dashboard.
    Using func.count() is much faster than fetching all rows.
    """
    total_channels = db.query(func.count(YoutubeChannel.channel_id)).scalar()
    total_leads = db.query(func.count(Lead.id)).scalar()
    total_emails = db.query(func.count(ExtractedEmail.id)).scalar()
    
    # Calculate "Hot Leads" (Email OR Instagram present)
    hot_leads = db.query(func.count(YoutubeChannel.channel_id))\
        .filter((YoutubeChannel.has_email == True) | (YoutubeChannel.has_instagram == True))\
        .scalar()

    return {
        "total_channels": total_channels,
        "total_leads": total_leads,
        "total_emails": total_emails,
        "hot_opportunities": hot_leads
    }

# ---------------------------------------------------------
# 2. CHART DATA (Last 30 Days Growth)
# ---------------------------------------------------------
@router.get("/growth-chart")
def get_growth_chart(days: int = 30, db: Session = Depends(get_db)):
    """
    Returns data formatted specifically for Recharts/Chart.js
    """
    start_date = date.today() - timedelta(days=days)

    stats = db.query(DailyStats)\
        .filter(DailyStats.stat_date >= start_date)\
        .order_by(DailyStats.stat_date.asc())\
        .all()

    chart_data = []
    for s in stats:
        chart_data.append({
            "date": s.stat_date.strftime("%Y-%m-%d"),
            "New Channels": s.channels_discovered,
            "Emails Found": s.emails_extracted,
            "Leads Generated": s.leads_created
        })

    return chart_data

# ---------------------------------------------------------
# 3. FUNNEL PERFORMANCE
# ---------------------------------------------------------
@router.get("/funnel")
def get_funnel_stats(db: Session = Depends(get_db)):
    """
    Shows conversion rates: Found -> Extracted -> Lead -> Contacted
    """
    channels = db.query(func.count(YoutubeChannel.channel_id)).scalar()
    with_email = db.query(func.count(YoutubeChannel.channel_id)).filter(YoutubeChannel.has_email == True).scalar()
    leads = db.query(func.count(Lead.id)).scalar()
    contacted = db.query(func.count(Lead.id)).filter(Lead.status == "contacted").scalar()

    return [
        {"stage": "Discovered", "value": channels, "fill": "#8884d8"},
        {"stage": "Has Email", "value": with_email, "fill": "#82ca9d"},
        {"stage": "Qualified Lead", "value": leads, "fill": "#ffc658"},
        {"stage": "Contacted", "value": contacted, "fill": "#ff8042"},
    ]