import sys
import os

# Ensure project root is in path
sys.path.append(os.getcwd())

from app.core.database import SessionLocal

# EXPLICIT IMPORTS TO FIX THE MAPPING ERROR
from app.models.target_category import TargetCategory
from app.models.youtube_channel import YoutubeChannel
from app.models.channel_social import ChannelSocialLink
from app.models.extracted_email import ExtractedEmail
from app.models.lead import Lead

def migrate():
    db = SessionLocal()
    print("🚀 Starting sync...")
    
    try:
        # 1. Sync Instagram (760 count)
        ig_links = db.query(ChannelSocialLink).filter(ChannelSocialLink.platform == "instagram").all()
        print(f"📊 Processing {len(ig_links)} Instagram links...")

        for link in ig_links:
            if not link.url: continue
            username = link.url.rstrip('/').split('/')[-1]
            
            lead = db.query(Lead).filter(Lead.channel_id == link.channel_id).first()
            if lead:
                lead.instagram_username = username
            else:
                new_lead = Lead(channel_id=link.channel_id, instagram_username=username, status="new")
                db.add(new_lead)

        # 2. Sync Emails (343 count)
        emails = db.query(ExtractedEmail).all()
        print(f"📊 Processing {len(emails)} extracted emails...")

        for e in emails:
            lead = db.query(Lead).filter(Lead.channel_id == e.channel_id).first()
            if lead:
                lead.primary_email = e.email
            else:
                new_lead = Lead(channel_id=e.channel_id, primary_email=e.email, status="new")
                db.add(new_lead)

        db.commit()
        print("🎉 Success! Your dashboards should now match.")
        
    except Exception as e:
        db.rollback()
        print(f"❌ Error: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    migrate()