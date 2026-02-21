import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, date
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.core.config import settings
from app.models.campaign import Campaign, CampaignLead, CampaignEvent
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
    campaign_lead_id, subject, html_body, to_email = lead_data
    
    try:
        success, error = email_service.send_email(to_email, subject, html_body)
        return campaign_lead_id, success, error
    except Exception as e:
        return campaign_lead_id, False, str(e)

def run_email_campaigns():
    db = SessionLocal()
    email_service = EmailService()
    
    try:
        # 1. Global Limit Check
        if not check_daily_limit(db):
            return

        # 2. Find Active Campaigns
        active_campaigns = db.query(Campaign).filter(
            Campaign.status == "running",
            Campaign.platform == "email"
        ).all()

        if not active_campaigns:
            return

        leads_to_process = []
        
        for campaign in active_campaigns:
            # --- A. Check for Completion (THE FIX) ---
            # Count leads that are NOT done (sent/failed)
            # We exclude 'sent' and 'failed'. If 0 remain, the campaign is done.
            remaining_count = db.query(func.count(CampaignLead.id)).filter(
                CampaignLead.campaign_id == campaign.id,
                CampaignLead.status.notin_(["sent", "failed"])
            ).scalar()

            if remaining_count == 0:
                logger.info(f"🏁 Campaign {campaign.id} has finished! Marking as completed.")
                campaign.status = "completed"
                db.commit()
                continue # Move to next campaign

            # --- B. Process Leads ---
            template = campaign.email_template
            if not template:
                continue

            html_layout = template.body or "<div>{{content}}</div>"
            
            # Find batch of ready leads
            pending_leads = db.query(CampaignLead).filter(
                CampaignLead.campaign_id == campaign.id,
                CampaignLead.status.in_(["review_ready", "ready_to_send"])
            ).limit(20).all()
            
            for pl in pending_leads:
                # Prepare content
                body_content = pl.ai_generated_body
                subject_content = pl.ai_generated_subject or template.subject

                if not body_content:
                    # Skip empty content
                    continue
                
                # Merge HTML
                formatted_body = body_content.replace("\n", "<br/>")
                final_html = html_layout.replace("{{content}}", formatted_body)
                final_html = final_html.replace("{channel_name}", pl.lead.channel_id)

                if pl.lead.primary_email:
                    leads_to_process.append((pl.id, subject_content, final_html, pl.lead.primary_email))
                else:
                    pl.status = "failed"
                    pl.error_message = "No email address found"
                    db.commit()

        # 3. Send Emails (Threaded)
        if not leads_to_process:
            return

        logger.info(f"🚀 Sending {len(leads_to_process)} emails...")
        
        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = [
                executor.submit(process_single_email, item, email_service) 
                for item in leads_to_process
            ]
            
            for future in as_completed(futures):
                lead_id, success, error = future.result()
                lead_record = db.query(CampaignLead).get(lead_id)
                
                if success:
                    lead_record.status = "sent"
                    lead_record.sent_at = datetime.utcnow()
                    
                    event = CampaignEvent(
                        campaign_lead_id=lead_id,
                        event_type="sent_email",
                        created_at=datetime.utcnow()
                    )
                    db.add(event)
                    lead_record.campaign.sent_count += 1
                    logger.info(f"✅ Sent to Lead {lead_id}")
                else:
                      
                    if error and "RECIPIENT_NOT_FOUND" in str(error):
                        lead_record.status = "invalid_email"
                    else:
                        lead_record.status = "failed"
                    lead_record.error_message = error
                    db.add(CampaignEvent(
                        campaign_lead_id=lead_id,
                        event_type="failed_email",
                        metadata_json={"error": str(error)}
                    ))
                    logger.error(f"❌ Failed Lead {lead_id}: {error}")

                db.commit()

    except Exception as e:
        logger.error(f"Worker Error: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    run_email_campaigns()