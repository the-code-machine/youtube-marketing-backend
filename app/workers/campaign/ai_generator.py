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
                # Updated to include Uday, Glossour, and specific services
                system_instruction = (
                    "You are Uday, the Outreach Manager at Glossour, a premier digital marketing agency. "
                    "Write a personalized, high-conversion email body to a YouTube creator. "
                    "OBJECTIVE: Offer them services to grow their channel using genuine strategies "
                    "(specifically Google Ads campaigns, increasing genuine views, and organic growth). "
                    "GUIDELINES: "
                    "1. Use the provided notes to write a specific, genuine compliment about their recent content. "
                    "2. Explain briefly how Glossour helps creators scale with legitimate ad strategies (no bots). "
                    "3. Keep the tone professional, encouraging, and concise. "
                    "4. Do NOT include a subject line in the body. "
                    "5. Sign off strictly as:\n"
                    "   Best regards,\n"
                    "   Uday\n"
                    "   Outreach Manager\n"
                    "   glossour.com"
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
                # We ask for a subject line relevant to growth/marketing
                subject_text = llm.generate_outreach(
                    system_prompt="Generate a catchy, short (under 6 words) subject line about YouTube Growth or Partnership. Do not use quotes.",
                    user_context=body_text 
                )

                # 6. Save Draft & Set to REVIEW
                item.ai_generated_body = body_text
                item.ai_generated_subject = subject_text.replace('"', '').strip()
                item.status = "review_ready" 
                
                item.campaign.generated_count += 1
                db.commit()
                
                # Sleep to respect rate limits
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