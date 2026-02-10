from datetime import datetime
from sqlalchemy.dialects.postgresql import insert
from app.models import YoutubeChannel, YoutubeVideo, ExtractedEmail, ChannelSocialLink, ChannelMetrics

def obj_to_dict(obj):
    # This automatically grabs 'category_id' if it exists in your Model definition
    return {c.name: getattr(obj, c.name) for c in obj.__table__.columns}

def bulk_write_all(db, p):
    
    # ---------------------------------------------------------
    # 1. CHANNELS (The Fix is Here)
    # ---------------------------------------------------------
    if p["channels"]:
        rows = [obj_to_dict(c) for c in p["channels"]]
        
        stmt = insert(YoutubeChannel).values(rows)
        
        stmt = stmt.on_conflict_do_update(
            index_elements=["channel_id"],
            set_={
                # Standard Metrics
                "subscriber_count": stmt.excluded.subscriber_count,
                "total_video_count": stmt.excluded.total_video_count,
                "total_view_count": stmt.excluded.total_view_count,
                
                # --- CRITICAL ADDITION ---
                # This updates the category even if the channel existed before
                "category_id": stmt.excluded.category_id,
                
                "updated_at": datetime.utcnow()
            }
        )
        db.execute(stmt)

    # ---------------------------------------------------------
    # 2. VIDEOS
    # ---------------------------------------------------------
    if p["videos"]:
        rows = [obj_to_dict(v) for v in p["videos"]]

        stmt = insert(YoutubeVideo).values(rows)
        stmt = stmt.on_conflict_do_nothing(index_elements=["video_id"])
        db.execute(stmt)

    # ---------------------------------------------------------
    # 3. EMAILS
    # ---------------------------------------------------------
    if p["emails"]:
        # Helper to ensure we don't crash on duplicates
        rows = [{"channel_id": e.channel_id, "email": e.email} for e in p["emails"]]
        if rows:
            stmt = insert(ExtractedEmail).values(rows)
            # Emails are unique per channel? Usually simple DO NOTHING is safe
            stmt = stmt.on_conflict_do_nothing() 
            db.execute(stmt)

    # ---------------------------------------------------------
    # 4. SOCIAL LINKS
    # ---------------------------------------------------------
    if p["socials"]:
        rows = [{"channel_id": s.channel_id, "platform": s.platform, "url": s.url} for s in p["socials"]]
        if rows:
            stmt = insert(ChannelSocialLink).values(rows)
            stmt = stmt.on_conflict_do_nothing()
            db.execute(stmt)

    # ---------------------------------------------------------
    # 5. METRICS (History)
    # ---------------------------------------------------------
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