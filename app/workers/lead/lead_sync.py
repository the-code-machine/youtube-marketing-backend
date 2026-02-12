from app.models.lead import Lead
from app.models.extracted_email import ExtractedEmail
from app.models.channel_social import ChannelSocialLink
from app.models.youtube_video import YoutubeVideo
import datetime

def sync_video_to_lead(db, video_id: str):
    # 1. Check if this specific VIDEO has already triggered a lead
    existing_lead = db.query(Lead).filter(Lead.video_id == video_id).first()
    if existing_lead:
        return # Skip, we already have a lead for this specific upload

    # 2. Get Video/Channel Context
    video = db.query(YoutubeVideo).filter(YoutubeVideo.video_id == video_id).first()
    if not video:
        return

    channel_id = video.channel_id

    # 3. Create the Lead
    new_lead = Lead(
        channel_id=channel_id,
        video_id=video_id, # Linking the lead to the video
        status="new",
        created_at=datetime.datetime.utcnow(),
        notes=f"Triggered by video: {video.title}"
    )
    
    # 4. Fetch Contact Info
    email_entry = db.query(ExtractedEmail.email).filter(ExtractedEmail.channel_id == channel_id).first()
    if email_entry:
        new_lead.primary_email = email_entry[0]
            
    ig_entry = db.query(ChannelSocialLink.url).filter(
        ChannelSocialLink.channel_id == channel_id, 
        ChannelSocialLink.platform == "instagram"
    ).first()
    
    if ig_entry:
        username = ig_entry[0].rstrip('/').split('/')[-1]
        new_lead.instagram_username = username

    db.add(new_lead)
    db.commit()