from sqlalchemy.orm import Session
from app.models import (
    Lead,
    YoutubeChannel,
    YoutubeVideo,
    ExtractedEmail,
    ChannelSocialLink
)
from datetime import datetime


def build_leads(db: Session):

    channels = (
        db.query(YoutubeChannel)
        .filter(
            (YoutubeChannel.has_email == True) |
            (YoutubeChannel.has_instagram == True)
        )
        .all()
    )

    created = 0

    for ch in channels:

        # Skip existing leads
        if db.query(Lead).filter(Lead.channel_id == ch.channel_id).first():
            continue

        latest_video = (
            db.query(YoutubeVideo)
            .filter(YoutubeVideo.channel_id == ch.channel_id)
            .order_by(YoutubeVideo.published_at.desc())
            .first()
        )

        email = (
            db.query(ExtractedEmail.email)
            .filter(ExtractedEmail.channel_id == ch.channel_id)
            .first()
        )

        ig = (
            db.query(ChannelSocialLink.username)
            .filter(
                ChannelSocialLink.channel_id == ch.channel_id,
                ChannelSocialLink.platform == "instagram"
            )
            .first()
        )

        if not email and not ig:
            continue

        context = f"""
Channel: {ch.name}
Country: {ch.country_code}
Subscribers: {ch.subscriber_count}

Latest Video:
Title: {latest_video.title if latest_video else ''}
Published: {latest_video.published_at if latest_video else ''}

Description:
{latest_video.description if latest_video else ''}

Tags:
{",".join(latest_video.tags or []) if latest_video else ''}
"""

        lead = Lead(
            channel_id=ch.channel_id,
            primary_email=email[0] if email else None,
            instagram_username=ig[0] if ig else None,
            status="new",
            notes=context.strip(),
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )

        db.add(lead)
        created += 1

    db.commit()

    print(f"Leads created: {created}")
