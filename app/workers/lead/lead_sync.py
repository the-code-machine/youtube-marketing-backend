from app.models.lead import Lead
from app.models.extracted_email import ExtractedEmail
from app.models.channel_social import ChannelSocialLink
import datetime

def sync_channel_to_lead(db, channel_id: str):
    # Fetch the lead or create a new one
    lead = db.query(Lead).filter(Lead.channel_id == channel_id).first()
    if not lead:
        lead = Lead(channel_id=channel_id, status="new", created_at=datetime.datetime.utcnow())
        db.add(lead)

    # Update Email if lead doesn't have one yet
    if not lead.primary_email:
        email_entry = db.query(ExtractedEmail).filter(ExtractedEmail.channel_id == channel_id).first()
        if email_entry:
            lead.primary_email = email_entry.email

    # Update Instagram if lead doesn't have one yet
    if not lead.instagram_username:
        ig_entry = db.query(ChannelSocialLink).filter(
            ChannelSocialLink.channel_id == channel_id, 
            ChannelSocialLink.platform == "instagram"
        ).first()
        if ig_entry:
            # Strip URL to get username: https://instagram.com/user -> user
            username = ig_entry.url.rstrip('/').split('/')[-1]
            lead.instagram_username = username

    db.commit()