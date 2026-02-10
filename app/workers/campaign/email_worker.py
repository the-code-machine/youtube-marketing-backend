import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, date
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.core.config import settings
from app.models.campaign import Campaign, CampaignLead, CampaignEvent, OutreachTemplate
from app.services.email_service import EmailService

# Configure Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def check_daily_limit(db: Session) -> bool:
    """Returns True if we are UNDER the limit, False if we hit it."""
    today = date.today()
    
    sent_count = db.query(func.count(CampaignEvent.id)).filter(
        CampaignEvent.event_type == "sent_email",
        func.date(CampaignEvent.created_at) == today
    ).scalar()
    
    if sent_count >= settings.DAILY_EMAIL_LIMIT:
        logger.warning(f"🚫 Daily Email Limit Reached: {sent_count}/{settings.DAILY_EMAIL_LIMIT}")
        return False
    
    return True

def process_single_email(lead_data, email_service):
    """
    Helper function to run inside a Thread.
    """
    campaign_lead, subject, body, to_email = lead_data
    
    success, error = email_service.send_email(to_email, subject, body)
    
    return campaign_lead.id, success, error

def run_email_campaigns():
    db = SessionLocal()
    email_service = EmailService()
    
    try:
        # 1. Global Limit Check
        if not check_daily_limit(db):
            return

        # 2. Find Active Campaigns (Email Platform)
        active_campaigns = db.query(Campaign).filter(
            Campaign.status == "running",
            Campaign.platform == "email"
        ).all()

        if not active_campaigns:
            logger.info("No active email campaigns found.")
            return

        # 3. Collect Leads to Send
        # We process batches of 20 to prevent memory overload
        leads_to_process = []
        
        for campaign in active_campaigns:
            # Find leads that are 'ready_to_send' 
            # (Meaning AI has generated content OR it's a static template)
            pending_leads = db.query(CampaignLead).filter(
                CampaignLead.campaign_id == campaign.id,
                CampaignLead.status == "ready_to_send"
            ).limit(20).all() # Small batch per run
            
            for pl in pending_leads:
                # Use AI content if available, else static template fallback
                subject = pl.ai_generated_subject or campaign.template.subject_template
                body = pl.ai_generated_body or campaign.template.body_template
                
                # Basic Variable Replacement (if not AI generated)
                if not pl.ai_generated_body:
                    # You would expand this logic for proper variable injection
                    body = body.replace("{name}", pl.lead.channel_id) 
                
                # Check if we have an email
                if pl.lead.primary_email:
                    leads_to_process.append((pl, subject, body, pl.lead.primary_email))
                else:
                    pl.status = "failed"
                    pl.error_message = "No email address found"
                    db.commit()

        if not leads_to_process:
            return

        # 4. Threaded Execution
        logger.info(f"🚀 Sending {len(leads_to_process)} emails...")
        
        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = [
                executor.submit(process_single_email, item, email_service) 
                for item in leads_to_process
            ]
            
            for future in as_completed(futures):
                lead_id, success, error = future.result()
                
                # Re-fetch lead to avoid detached instance issues
                lead_record = db.query(CampaignLead).get(lead_id)
                
                if success:
                    lead_record.status = "sent"
                    lead_record.sent_at = datetime.utcnow()
                    
                    # Log Event
                    event = CampaignEvent(
                        campaign_lead_id=lead_id,
                        event_type="sent_email",
                        created_at=datetime.utcnow()
                    )
                    db.add(event)
                    
                    # Update Campaign Counter
                    lead_record.campaign.sent_count += 1
                    
                else:
                    lead_record.status = "failed"
                    lead_record.error_message = error
                    
                    event = CampaignEvent(
                        campaign_lead_id=lead_id,
                        event_type="failed_email",
                        metadata_json={"error": error},
                        created_at=datetime.utcnow()
                    )
                    db.add(event)

                db.commit()

    except Exception as e:
        logger.error(f"Critical Worker Error: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    run_email_campaigns()