import time
from datetime import datetime
from sqlalchemy.orm import Session
from app.core.database import SessionLocal
from app.models.campaign import Campaign, CampaignLead
from app.models.script_plan_model import ScriptPlan
from app.models.youtube_channel import YoutubeChannel
from app.models.youtube_video import YoutubeVideo
from app.models.ai_usage import AIUsageLog
from app.services.llm_service import LLMService


def estimate_tokens(text: str) -> int:
    return len(text) if text else 0


def _fmt_num(n) -> str:
    if not n: return "0"
    n = int(n)
    if n >= 1_000_000: return f"{n/1_000_000:.1f}M"
    if n >= 1_000: return f"{n/1_000:.0f}k"
    return str(n)


def _fmt_dur(sec) -> str:
    if not sec: return "unknown"
    sec = int(sec)
    m, s = divmod(sec, 60)
    if m >= 60:
        h, m = divmod(m, 60)
        return f"{h}h {m}m"
    return f"{m}m {s}s" if s else f"{m}m"


def _calc_price(plan: ScriptPlan, view_count: int) -> str:
    """Resolve a human-readable price string from the plan's pricing model."""
    views = view_count or 0
    price = 0.0
    sym = plan.currency or "USD"

    if plan.pricing_model == "flat_rate":
        price = plan.base_price or 0
    elif plan.pricing_model == "per_view":
        price = views * (plan.price_per_view or 0)
    elif plan.pricing_model == "per_1k_views":
        price = (views / 1000) * (plan.price_per_1k or 0)
    elif plan.pricing_model == "revenue_share":
        return f"{plan.revenue_share_pct or 0}% revenue share"
    elif plan.pricing_model == "negotiable":
        return "negotiable — open to discuss"

    # Apply floor guarantee
    if plan.min_guarantee and price < plan.min_guarantee:
        price = plan.min_guarantee

    return f"{sym} {price:,.2f}" if price > 0 else "negotiable"


def _fill_template(template: str, variables: dict) -> str:
    """Replace {{var}} tokens in a template with actual values."""
    for key, val in variables.items():
        template = template.replace(f"{{{{{key}}}}}", str(val) if val is not None else "N/A")
    return template


def _build_script_plan_prompts(item: CampaignLead, plan: ScriptPlan, db: Session):
    """
    Build system + user prompts using the script plan's template.
    Fetches channel and video data, fills all {{variables}}, returns (system, user).
    """
    lead = item.lead

    # Pull channel and latest video
    channel = db.query(YoutubeChannel).filter(
        YoutubeChannel.channel_id == lead.channel_id
    ).first()

    video = db.query(YoutubeVideo).filter(
        YoutubeVideo.channel_id == lead.channel_id
    ).order_by(YoutubeVideo.published_at.desc()).first()

    subs = channel.subscriber_count if channel else 0
    views = video.view_count if video else 0
    engagement = round((views / subs * 100), 1) if subs > 0 else 0.0
    calculated_price = _calc_price(plan, views)

    variables = {
        "channel_name":      channel.name if channel else lead.channel_id,
        "subscriber_count":  _fmt_num(subs),
        "view_count":        _fmt_num(views),
        "video_title":       video.title if video else "their latest video",
        "video_duration":    _fmt_dur(video.duration_seconds if video else None),
        "country":           (channel.country_code or "N/A") if channel else "N/A",
        "video_tags":        ", ".join((video.tags or [])[:5]) if video else "N/A",
        "calculated_price":  calculated_price,
        "engagement_rate":   f"{engagement}%",
        "service_type":      plan.service_type.replace("_", " ").title(),
        "pitch_angle":       (plan.pitch_angle or "value-based").replace("_", " ").title(),
    }

    # System: filled prompt template instructs the LLM how to write
    system_prompt = _fill_template(plan.ai_prompt_template, variables)

    # User: the channel notes context (same as generalised mode)
    user_context = f"""
Channel: {variables['channel_name']}
Country: {variables['country']}
Subscribers: {variables['subscriber_count']}
Latest Video: "{variables['video_title']}" ({variables['video_duration']}, {variables['view_count']} views)
Tags: {variables['video_tags']}
Engagement Rate: {variables['engagement_rate']}
Our Offer: {variables['calculated_price']} for a {variables['service_type']}

Write a personalized email based on the above. Do NOT include a subject line in the body.
Sign off as:
  Best regards,
  Uday
  Outreach Manager
  glossour.com
""".strip()

    # Subject prompt (separate call)
    subject_hint = ""
    if plan.email_subject_template:
        subject_hint = _fill_template(plan.email_subject_template, variables)

    return system_prompt, user_context, subject_hint


def _build_generalised_prompts(item: CampaignLead):
    """Original hardcoded prompts — unchanged from existing behaviour."""
    lead_notes = item.lead.notes or "No specific notes available."
    channel_name = item.lead.channel_id

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
""".strip()

    return system_instruction, user_context, ""


# ─── MAIN WORKER ──────────────────────────────────────────────────────────────

def run_ai_generation():
    db = SessionLocal()
    llm = LLMService()

    PRICE_PER_1M_INPUT  = 0.14
    PRICE_PER_1M_OUTPUT = 0.28

    try:
        queue = db.query(CampaignLead).filter(
            CampaignLead.status == "queued"
        ).limit(10).all()

        if not queue:
            return

        print(f"🤖 Generating AI drafts for {len(queue)} leads...")

        for item in queue:
            try:
                # ── Determine mode from parent campaign ─────────────────────
                campaign = db.query(Campaign).get(item.campaign_id)
                mode = getattr(campaign, "generation_mode", "generalised") or "generalised"
                plan_id = getattr(campaign, "script_plan_id", None)

                if mode == "script_plan" and plan_id:
                    # ── SCRIPT PLAN MODE ─────────────────────────────────────
                    plan = db.query(ScriptPlan).get(plan_id)
                    if not plan:
                        # Plan deleted? Fall back gracefully
                        print(f"⚠️  Plan {plan_id} not found, falling back to generalised")
                        system_instruction, user_context, subject_hint = _build_generalised_prompts(item)
                    else:
                        system_instruction, user_context, subject_hint = _build_script_plan_prompts(item, plan, db)
                        # Increment usage counter
                        plan.total_used = (plan.total_used or 0) + 1
                else:
                    # ── GENERALISED MODE (default) ────────────────────────────
                    system_instruction, user_context, subject_hint = _build_generalised_prompts(item)

                # ── Generate body ─────────────────────────────────────────────
                body_text = llm.generate_outreach(
                    system_prompt=system_instruction,
                    user_context=user_context
                )

                # ── Generate subject ──────────────────────────────────────────
                if subject_hint:
                    # Use plan's subject template hint as a seeding context
                    subject_text = llm.generate_outreach(
                        system_prompt=f"Generate a short (under 8 words), compelling email subject line. "
                                      f"Base it on this hint: '{subject_hint}'. "
                                      f"Do not use quotes. Output only the subject line.",
                        user_context=body_text
                    )
                else:
                    subject_text = llm.generate_outreach(
                        system_prompt="Generate a catchy, short (under 6 words) subject line about YouTube Growth or Partnership. Do not use quotes.",
                        user_context=body_text
                    )

                # ── Calculate usage & cost ────────────────────────────────────
                input_str   = system_instruction + user_context
                output_str  = body_text + subject_text
                input_tokens  = estimate_tokens(input_str)
                output_tokens = estimate_tokens(output_str)
                total_tokens  = input_tokens + output_tokens
                cost = (input_tokens / 1_000_000 * PRICE_PER_1M_INPUT) + \
                       (output_tokens / 1_000_000 * PRICE_PER_1M_OUTPUT)

                # ── Log usage ─────────────────────────────────────────────────
                db.add(AIUsageLog(
                    task_type=f"outreach_generation_{mode}",
                    model_name="deepseek-chat",
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    total_tokens=total_tokens,
                    estimated_cost=round(cost, 6),
                    related_channel_id=item.lead.channel_id,
                    status="success",
                    created_at=datetime.utcnow()
                ))

                # ── Save result ───────────────────────────────────────────────
                item.ai_generated_body    = body_text
                item.ai_generated_subject = subject_text.replace('"', '').strip()
                item.status               = "review_ready"
                item.campaign.generated_count = (item.campaign.generated_count or 0) + 1

                db.commit()
                time.sleep(0.5)

            except Exception as e:
                print(f"❌ AI Error lead {item.id}: {e}")
                db.add(AIUsageLog(
                    task_type="outreach_generation_failed",
                    model_name="deepseek-chat",
                    input_tokens=0, output_tokens=0,
                    estimated_cost=0.0,
                    related_channel_id=item.lead.channel_id,
                    status="failed",
                    created_at=datetime.utcnow()
                ))
                item.status        = "failed"
                item.error_message = str(e)
                db.commit()

    except Exception as e:
        print(f"Worker Error: {e}")
    finally:
        db.close()


if __name__ == "__main__":
    run_ai_generation()