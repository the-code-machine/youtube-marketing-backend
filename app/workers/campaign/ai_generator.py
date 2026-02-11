import time
from datetime import datetime
from sqlalchemy.orm import Session
from app.core.database import SessionLocal
from app.models.campaign import CampaignLead
# ✅ Import the new Usage Log Model
from app.models.ai_usage import AIUsageLog 
from app.services.llm_service import LLMService

def estimate_tokens(text: str) -> int:
    """
    Standard estimation: 1 token ~= 4 characters (English).
    """
    if not text:
        return 0
    return len(text) 

def run_ai_generation():
    db = SessionLocal()
    llm = LLMService()
    
    # Pricing Configuration (Example: DeepSeek Chat V3 Pricing)
    # Adjust these values based on your actual provider
    PRICE_PER_1M_INPUT = 0.14  # $0.14 per 1M input tokens
    PRICE_PER_1M_OUTPUT = 0.28 # $0.28 per 1M output tokens
    
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
                # 2. Prepare Data
                lead_notes = item.lead.notes or "No specific notes available."
                channel_name = item.lead.channel_id
                
                # --- PROMPTS ---
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
                
                # --- GENERATION 1: BODY ---
                body_start = time.time()
                body_text = llm.generate_outreach(
                    system_prompt=system_instruction,
                    user_context=user_context
                )
                
                # --- GENERATION 2: SUBJECT ---
                subject_prompt = "Generate a catchy, short (under 6 words) subject line about YouTube Growth or Partnership. Do not use quotes."
                subject_text = llm.generate_outreach(
                    system_prompt=subject_prompt,
                    user_context=body_text 
                )

                # --- 3. CALCULATE USAGE (Estimation) ---
                # Inputs
                input_str = system_instruction + user_context + subject_prompt + body_text
                input_tokens = estimate_tokens(input_str)
                
                # Outputs
                output_str = body_text + subject_text
                output_tokens = estimate_tokens(output_str)
                
                total_tokens = input_tokens + output_tokens
                
                # Calculate Cost
                cost = (input_tokens / 1_000_000 * PRICE_PER_1M_INPUT) + \
                       (output_tokens / 1_000_000 * PRICE_PER_1M_OUTPUT)

                # --- 4. LOG USAGE TO DB ---
                usage_log = AIUsageLog(
                    task_type="outreach_generation",
                    model_name="deepseek-chat", # Or fetch from config
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    total_tokens=total_tokens,
                    estimated_cost=round(cost, 6), # Precision to 6 decimals
                    related_channel_id=channel_name,
                    related_video_id=None, # Add if you have it in Lead
                    status="success",
                    created_at=datetime.utcnow()
                )
                db.add(usage_log)

                # --- 5. SAVE DRAFT ---
                item.ai_generated_body = body_text
                item.ai_generated_subject = subject_text.replace('"', '').strip()
                item.status = "review_ready" 
                
                item.campaign.generated_count += 1
                
                db.commit()
                
                # Sleep to respect rate limits
                time.sleep(0.5)

            except Exception as e:
                print(f"❌ AI Error lead {item.id}: {e}")
                
                # Log Failure Usage (Optional, assuming 0 output)
                error_log = AIUsageLog(
                    task_type="outreach_generation_failed",
                    model_name="deepseek-chat",
                    input_tokens=0,
                    output_tokens=0,
                    estimated_cost=0.0,
                    related_channel_id=item.lead.channel_id,
                    status="failed",
                    created_at=datetime.utcnow()
                )
                db.add(error_log)
                
                item.status = "failed"
                item.error_message = str(e)
                db.commit()

    except Exception as e:
        print(f"Worker Error: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    run_ai_generation()