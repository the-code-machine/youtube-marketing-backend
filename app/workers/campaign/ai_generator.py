import time
from sqlalchemy.orm import Session
from app.core.database import SessionLocal
from app.models.campaign import Campaign, CampaignLead
from app.services.llm_service import LLMService

def run_ai_generation():
    """
    Worker that finds 'queued' leads and uses LLM to write initial drafts.
    These drafts are saved as 'review_ready' for human approval.
    """
    db = SessionLocal()
    llm = LLMService()
    
    try:
        # 1. Fetch leads waiting for AI ("queued")
        # We limit the batch size to keep the worker lightweight and responsive
        queue = db.query(CampaignLead).filter(
            CampaignLead.status == "queued"
        ).limit(10).all()
        
        if not queue:
            # If nothing to do, just return silently
            return

        print(f"🤖 Generating AI drafts for {len(queue)} leads...")

        for item in queue:
            try:
                # 2. Access the Campaign -> EmailTemplate Relationship
                # We need the 'ai_prompt_instructions' from the template
                campaign = item.campaign
                template = campaign.email_template
                lead = item.lead
                
                # Validation: Does the template support AI?
                if not template or not template.ai_prompt_instructions:
                    print(f"⚠️ Skipping Lead {item.id}: Template missing AI instructions.")
                    item.status = "failed"
                    item.error_message = "Template missing AI instructions"
                    db.commit()
                    continue

                # 3. Build Context (The "User Prompt")
                # This provides the LLM with specific details about THIS lead
                # You can expand this to include video titles, subscriber counts, etc.
                context = f"""
                Channel Name: {lead.channel_id}
                Notes/Context: {lead.notes or "No specific notes available."}
                Platform: {campaign.platform}
                """
                
                # 4. Generate Body Content
                # We pass the instruction from DB as system prompt
                body_text = llm.generate_outreach(
                    system_prompt=template.ai_prompt_instructions,
                    user_context=context
                )
                
                # 5. Generate Subject Line (if Email)
                subject_text = ""
                if campaign.platform == 'email':
                    subject_text = llm.generate_outreach(
                        system_prompt="Generate a short, engaging, 5-7 word subject line for a sponsorship inquiry. Do not use quotes.",
                        user_context=context
                    )
                    subject_text = subject_text.replace('"', '').strip()

                # 6. Save Draft & Update Status
                item.ai_generated_body = body_text
                item.ai_generated_subject = subject_text
                
                # CRITICAL: We set it to 'review_ready', NOT 'sent'
                # This ensures the human can review it on the UI before sending
                item.status = "review_ready" 
                
                # Increment counter for UI stats
                campaign.generated_count += 1
                db.commit()
                
                # Sleep briefly to be kind to the LLM API rate limits
                time.sleep(0.5)

            except Exception as e:
                print(f"❌ Generation Failed for Lead {item.id}: {str(e)}")
                item.status = "failed"
                item.error_message = f"AI Generation Error: {str(e)}"
                db.commit()

    except Exception as e:
        print(f"🔥 Critical AI Worker Error: {str(e)}")
    finally:
        db.close()

if __name__ == "__main__":
    run_ai_generation()