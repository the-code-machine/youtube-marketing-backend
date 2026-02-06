from datetime import date, datetime
from sqlalchemy.orm import Session
from app.models import DailyStats, CountryStats, CategoryStats


def nz(v):
    return v if v else 0


def write_stats(db: Session, payload, category_name):

    today = date.today()

    channels = payload["channels"]
    videos = payload["videos"]
    emails = payload["emails"]

    # ---------------- DAILY STATS

    daily = db.query(DailyStats).filter(DailyStats.stat_date == today).first()

    if not daily:
        daily = DailyStats(stat_date=today)
        db.add(daily)
        db.flush()

    daily.channels_discovered = nz(daily.channels_discovered) + len(channels)
    daily.videos_fetched = nz(daily.videos_fetched) + len(videos)
    daily.emails_extracted = nz(daily.emails_extracted) + len(emails)
    daily.jobs_run = nz(daily.jobs_run) + 1
    daily.updated_at = datetime.utcnow()

    # ---------------- CATEGORY STATS

    cat = db.query(CategoryStats).filter(
        CategoryStats.stat_date == today,
        CategoryStats.category == category_name
    ).first()

    if not cat:
        cat = CategoryStats(stat_date=today, category=category_name)
        db.add(cat)
        db.flush()

    cat.channels_discovered = nz(cat.channels_discovered) + len(channels)
    cat.videos_fetched = nz(cat.videos_fetched) + len(videos)
    cat.emails_extracted = nz(cat.emails_extracted) + len(emails)
    cat.updated_at = datetime.utcnow()

    # ---------------- COUNTRY STATS (from channels)

    for c in channels:

        if not c.country_code:
            continue

        cs = db.query(CountryStats).filter(
            CountryStats.stat_date == today,
            CountryStats.country_code == c.country_code
        ).first()

        if not cs:
            cs = CountryStats(
                stat_date=today,
                country_code=c.country_code,
                country_name=c.country_code
            )
            db.add(cs)
            db.flush()

        cs.channels_discovered = nz(cs.channels_discovered) + 1
        cs.updated_at = datetime.utcnow()

    db.commit()
