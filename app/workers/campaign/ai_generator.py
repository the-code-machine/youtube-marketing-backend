import time
from sqlalchemy.orm import Session
from app.core.database import SessionLocal
from app.models.campaign import CampaignLead
from app.services.llm_service import LLMService

def run_ai_generation():
    db = SessionLocal()
    llm = LLMService()
    
    try:
        # 1. Fetch leads waiting for AI ("queued")
        queue = db.query(CampaignLead).filter(
            CampaignLead.status == "queued"
        ).limit(10).all()
        
        if not queue:
            return

        print(f"🤖 Generating AI drafts for {len(queue)} leads...")

        for item in queue:
            try:
                # 2. Get the Lead Data (The Source of Truth)
                lead_notes = item.lead.notes or "No specific notes available."
                channel_name = item.lead.channel_id
                
                # 3. Define the Prompt
                # We tell the AI to use the NOTES to write the email.
                system_instruction = (
                    "You are an expert outreach manager. "
                    "Write a personalized email body based on the notes provided about the creator. "
                    "Do not include the subject line in the body. Keep it professional yet friendly."
                )
                
                user_context = f"""
                Creator Name: {channel_name}
                Analysis/Notes: {lead_notes}
                """
                
                # 4. Generate Body
                body_text = llm.generate_outreach(
                    system_prompt=system_instruction,
                    user_context=user_context
                )
                
                # 5. Generate Subject
                subject_text = llm.generate_outreach(
                    system_prompt="Generate a catchy 5-word subject line for this email.",
                    user_context=body_text # Base subject on the body we just wrote
                )

                # 6. Save Draft & Set to REVIEW
                item.ai_generated_body = body_text
                item.ai_generated_subject = subject_text.replace('"', '').strip()
                item.status = "review_ready" # <--- Human must review next
                
                item.campaign.generated_count += 1
                db.commit()
                time.sleep(0.5)

            except Exception as e:
                print(f"❌ AI Error lead {item.id}: {e}")
                item.status = "failed"
                item.error_message = str(e)
                db.commit()

    except Exception as e:
        print(f"Worker Error: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    run_ai_generation()