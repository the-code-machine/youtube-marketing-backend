import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, date
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.core.config import settings
from app.models.campaign import Campaign, CampaignLead, CampaignEvent
# Note: Campaign now links to EmailTemplate via `email_template` relationship
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
    Sends the actual email via SMTP.
    """
    campaign_lead_id, subject, html_body, to_email = lead_data
    
    success, error = email_service.send_email(to_email, subject, html_body)
    
    return campaign_lead_id, success, error

def run_email_campaigns():
    db = SessionLocal()
    email_service = EmailService()
    
    try:
        # 1. Global Limit Check
        if not check_daily_limit(db):
            return

        # 2. Find Active Campaigns (Email Platform)
        # We only want campaigns that are explicitly set to "running"
        active_campaigns = db.query(Campaign).filter(
            Campaign.status == "running",
            Campaign.platform == "email"
        ).all()

        if not active_campaigns:
            logger.info("No active email campaigns found.")
            return

        # 3. Collect Leads to Send
        leads_to_process = []
        
        for campaign in active_campaigns:
            # Fetch the HTML wrapper from the template
            # Fallback to a simple div if body is missing
  
            
            # Find leads that are ready.
            # We look for 'review_ready' (AI done) OR 'ready_to_send' (Manual override)
            pending_leads = db.query(CampaignLead).filter(
    CampaignLead.campaign_id == campaign.id,
    CampaignLead.status == "ready_to_send" 
).limit(20).all()
            
            for pl in pending_leads:
                # 1. Validation
                if not pl.ai_generated_body:
                    pl.status = "failed"
                    pl.error_message = "No AI content found"
                    db.commit()
                    continue

                # 2. Fetch the HTML Template (The UI Wrapper)
                # This is where the template comes into the picture!
                html_wrapper = campaign.email_template.body or "<div>{{content}}</div>"
                
                # 3. Merge: HTML + AI Content
                # Convert newlines to <br> so the text looks good in HTML
                formatted_ai_text = pl.ai_generated_body.replace("\n", "<br/>")
                
                # Replace the placeholder in the template with the AI text
                final_email_html = html_wrapper.replace("{{content}}", formatted_ai_text)
                
                # 4. Send
                if pl.lead.primary_email:
                    leads_to_process.append((
                        pl.id, 
                        pl.ai_generated_subject, 
                        final_email_html, # Sending the merged result
                        pl.lead.primary_email
                    ))
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
                    
                    # Log Success Event
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
                    
                    # Log Failure Event
                    event = CampaignEvent(
                        campaign_lead_id=lead_id,
                        event_type="failed_email",
                        metadata_json={"error": str(error)},
                        created_at=datetime.utcnow()
                    )
                    db.add(event)

                db.commit()

    except Exception as e:
        logger.error(f"Critical Email Worker Error: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    run_email_campaigns()