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
            logger.info("ℹ️ No active email campaigns found.")
            return

        leads_to_process = []
        
        for campaign in active_campaigns:
            # ✅ FIX: Access the new 'email_template' relationship
            template = campaign.email_template
            if not template:
                logger.error(f"❌ Campaign {campaign.id} has no template attached. Skipping.")
                continue

            # Fallback HTML if body is empty
            html_layout = template.body or "<div>{{content}}</div>"
            
            # 3. Find Leads
            # We accept BOTH 'ready_to_send' (Manual) AND 'review_ready' (AI Auto-approved flow)
            pending_leads = db.query(CampaignLead).filter(
                CampaignLead.campaign_id == campaign.id,
                CampaignLead.status.in_(["review_ready", "ready_to_send"])
            ).limit(20).all()
            
            if not pending_leads:
                continue
                
            logger.info(f"🔎 Campaign {campaign.id}: Found {len(pending_leads)} leads to process.")

            for pl in pending_leads:
                # 🛑 SAFETY: Check if we have content
                body_content = pl.ai_generated_body
                subject_content = pl.ai_generated_subject or template.subject

                if not body_content:
                    logger.warning(f"⚠️ Skipping Lead {pl.id}: No AI body content found.")
                    # Optional: Mark as failed so we don't retry endlessly
                    # pl.status = "failed"
                    # pl.error_message = "Missing content"
                    # db.commit()
                    continue
                
                # 4. Merge Content into Template
                # Replace newlines with <br> for HTML
                formatted_body = body_content.replace("\n", "<br/>")
                
                # Inject into the Template Wrapper
                final_html = html_layout.replace("{{content}}", formatted_body)
                
                # Basic variable replacement (e.g. for Footer)
                final_html = final_html.replace("{channel_name}", pl.lead.channel_id)

                if pl.lead.primary_email:
                    leads_to_process.append((pl.id, subject_content, final_html, pl.lead.primary_email))
                else:
                    pl.status = "failed"
                    pl.error_message = "No email address found"
                    db.commit()

        if not leads_to_process:
            logger.info("ℹ️ No leads ready to send in active campaigns.")
            return

        # 5. Threaded Execution
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
                    lead_record.message_id = "sent-via-smtp" # Placeholder or actual ID
                    
                    # Log Event
                    event = CampaignEvent(
                        campaign_lead_id=lead_id,
                        event_type="sent_email",
                        created_at=datetime.utcnow()
                    )
                    db.add(event)
                    
                    # Update Campaign Counter
                    lead_record.campaign.sent_count += 1
                    logger.info(f"✅ Sent to Lead {lead_id}")
                    
                else:
                    lead_record.status = "failed"
                    lead_record.error_message = error
                    
                    event = CampaignEvent(
                        campaign_lead_id=lead_id,
                        event_type="failed_email",
                        metadata_json={"error": str(error)},
                        created_at=datetime.utcnow()
                    )
                    db.add(event)
                    logger.error(f"❌ Failed Lead {lead_id}: {error}")

                db.commit()

    except Exception as e:
        logger.error(f"🔥 Critical Email Worker Error: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    run_email_campaigns()