import datetime
from sqlalchemy.dialects.postgresql import insert
from app.models import YoutubeChannel, YoutubeVideo, ExtractedEmail, ChannelSocialLink
from app.models.channel_metrics import ChannelMetrics


def obj_to_dict(obj):
    return {c.name: getattr(obj, c.name) for c in obj.__table__.columns}


def bulk_write_all(db, p):

    # ---------------- CHANNELS
    if p["channels"]:
        rows = [obj_to_dict(c) for c in p["channels"]]
        stmt = insert(YoutubeChannel).values(rows)
        
        stmt = stmt.on_conflict_do_update(
            index_elements=["channel_id"],
            set_={
                "subscriber_count": stmt.excluded.subscriber_count,
                "video_count": stmt.excluded.total_video_count,
                "view_count": stmt.excluded.total_view_count,
                "updated_at": datetime.utcnow()
            }
        )
        db.execute(stmt)

    # ---------------- VIDEOS
    if p["videos"]:
        rows = [obj_to_dict(v) for v in p["videos"]]

        stmt = insert(YoutubeVideo).values(rows)
        stmt = stmt.on_conflict_do_nothing(index_elements=["video_id"])
        db.execute(stmt)

    # ---------------- EMAILS
    if p["emails"]:
        rows = [{"channel_id": e.channel_id, "email": e.email} for e in p["emails"]]

        stmt = insert(ExtractedEmail).values(rows)
        stmt = stmt.on_conflict_do_nothing()
        db.execute(stmt)

    # ---------------- SOCIAL LINKS
    if p["socials"]:
        rows = [{"channel_id": s.channel_id, "platform": s.platform, "url": s.url} for s in p["socials"]]

        stmt = insert(ChannelSocialLink).values(rows)
        stmt = stmt.on_conflict_do_nothing()
        db.execute(stmt)


    if p.get("metrics"):
        rows = [obj_to_dict(m) for m in p["metrics"]]
        stmt = insert(ChannelMetrics).values(rows)
        stmt = stmt.on_conflict_do_update(
            index_elements=["channel_id"],
            set_={
                "avg_views": stmt.excluded.avg_views,
                "engagement_rate": stmt.excluded.engagement_rate,
                "updated_at": datetime.utcnow()
            }
        )
        db.execute(stmt)

    db.commit()
