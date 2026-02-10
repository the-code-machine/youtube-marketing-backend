import time
from sqlalchemy.orm import Session
from app.core.database import SessionLocal
from app.models.campaign import Campaign, CampaignLead
from app.services.llm_service import LLMService

def run_ai_generation():
    db = SessionLocal()
    llm = LLMService()
    
    try:
        # 1. Find Leads waiting for AI ("queued")
        # We fetch 10 at a time to keep the worker responsive
        queue = db.query(CampaignLead).filter(
            CampaignLead.status == "queued"
        ).limit(10).all()
        
        if not queue:
            print("💤 No AI jobs pending.")
            return

        print(f"🤖 Generating AI content for {len(queue)} leads...")

        for item in queue:
            campaign = item.campaign
            lead = item.lead
            template = campaign.template
            
            # 2. Build Context (The "Prompt Engineering" Part)
            # We combine channel data + latest video context
            context = f"""
            Channel Name: {lead.channel_id} (This is actually the ID, ideally fetch Name)
            Context Notes: {lead.notes} (Contains latest video title/description)
            """
            
            try:
                # 3. Generate Subject (if Email)
                if campaign.platform == 'email':
                    subject = llm.generate_outreach(
                        system_prompt="Generate a short, catchy, non-spammy subject line for a sponsorship inquiry.",
                        user_context=context
                    )
                    item.ai_generated_subject = subject.replace('"', '') # Clean up quotes

                # 4. Generate Body
                body = llm.generate_outreach(
                    system_prompt=template.body_template, # The "System Instruction" from your DB
                    user_context=context
                )
                
                # 5. Save Draft
                item.ai_generated_body = body
                item.status = "ready_to_send" # Moved to next stage
                
                # Update Campaign Counter
                campaign.generated_count += 1
                db.commit()
                
                # Sleep to avoid Rate Limits on LLM API
                time.sleep(1)

            except Exception as e:
                print(f"❌ Generation Failed for Lead {item.id}: {e}")
                item.status = "failed"
                item.error_message = str(e)
                db.commit()

    except Exception as e:
        print(f"Worker Error: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    run_ai_generation()