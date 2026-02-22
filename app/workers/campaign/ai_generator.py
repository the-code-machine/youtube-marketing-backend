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


# ─── FORMATTERS ───────────────────────────────────────────────────────────────

def _fmt_num(n) -> str:
    if not n: return "0"
    n = int(n)
    if n >= 1_000_000: return f"{n/1_000_000:.1f}M"
    if n >= 1_000: return f"{n/1_000:.0f}k"
    return str(n)


def _fmt_dur(sec) -> str:
    if not sec: return "unknown duration"
    sec = int(sec)
    m, s = divmod(sec, 60)
    if m >= 60:
        h, m = divmod(m, 60)
        return f"{h}h {m}m"
    return f"{m}m {s}s" if s else f"{m}m"


def _dur_bucket(sec) -> str:
    """Classify duration into bucket key for multiplier lookup."""
    if not sec: return "mid"
    sec = int(sec)
    if sec < 60:    return "shorts"
    if sec < 300:   return "short"
    if sec < 900:   return "mid"
    if sec < 3600:  return "long"
    return "ultra"


def _sub_bucket(subs) -> str:
    """Classify subscriber count into bucket for multiplier lookup."""
    if not subs: return "small"
    subs = int(subs)
    if subs < 10_000:    return "tiny"
    if subs < 100_000:   return "small"
    if subs < 1_000_000: return "mid"
    if subs < 5_000_000: return "large"
    return "mega"


def _detect_language(channel) -> str:
    """
    Simple language detection from country code as proxy.
    Real implementation could use video language field if available.
    """
    english_countries = {"US", "GB", "AU", "CA", "NZ", "IE"}
    hindi_countries   = {"IN", "NP"}
    spanish_countries = {"ES", "MX", "AR", "CO", "CL", "PE"}
    portuguese_countries = {"BR", "PT"}

    cc = (channel.country_code or "").upper()
    if cc in english_countries:    return "en"
    if cc in hindi_countries:      return "hi"
    if cc in spanish_countries:    return "es"
    if cc in portuguese_countries: return "pt"
    return "default"


# ─── PRICING ENGINE ───────────────────────────────────────────────────────────

def calculate_price(plan: ScriptPlan, channel, video) -> tuple[float, dict]:
    """
    Calculate the final quote price and return a breakdown dict for transparency.

    Returns:
        (final_price: float, breakdown: dict)
    """
    view_target = plan.view_target or 1_000_000
    base_per_1k = plan.base_price_per_1k or 1.0
    subs        = channel.subscriber_count if channel else 0
    duration    = video.duration_seconds   if video   else None
    country     = (channel.country_code or "").upper() if channel else ""
    views       = video.view_count         if video   else 0
    engagement  = round((views / subs * 100), 1) if subs > 0 else 0.0

    # 1. Base cost for target volume
    base_cost = (view_target / 1000) * base_per_1k

    # 2. Country multiplier
    country_mults = plan.country_multipliers or {}
    country_mult  = country_mults.get(country, country_mults.get("default", 1.0))

    # 3. Duration multiplier
    dur_mults = plan.duration_multipliers or {}
    dur_key   = _dur_bucket(duration)
    dur_mult  = dur_mults.get(dur_key, 1.0)

    # 4. Niche multiplier (from channel category)
    niche_mults = plan.niche_multipliers or {}
    niche_key   = "default"
    if channel and channel.category:
        niche_key = channel.category.name.lower().replace(" ", "_")
    niche_mult = niche_mults.get(niche_key, niche_mults.get("default", 1.0))

    # 5. Platform multiplier
    platform_mult = plan.platform_multiplier or 1.0

    # 6. Delivery speed multiplier
    delivery_mult = plan.delivery_multiplier or 1.0

    # 7. Retention multiplier
    retention_mult = plan.retention_multiplier or 1.0

    # 8. Subscriber count multiplier
    sub_mults = plan.subscriber_multipliers or {}
    sub_key   = _sub_bucket(subs)
    sub_mult  = sub_mults.get(sub_key, 1.0)

    # 9. Language multiplier
    lang_mults = plan.language_multipliers or {}
    lang_key   = _detect_language(channel)
    lang_mult  = lang_mults.get(lang_key, lang_mults.get("default", 1.0))

    # 10. Apply all multipliers
    price = (base_cost
             * country_mult
             * dur_mult
             * niche_mult
             * platform_mult
             * delivery_mult
             * retention_mult
             * sub_mult
             * lang_mult)

    # 11. Volume discount on final price
    discount_pct = 0
    if plan.volume_discounts:
        for tier in sorted(plan.volume_discounts, key=lambda x: x["threshold"], reverse=True):
            if view_target >= tier["threshold"]:
                discount_pct = tier["discount_pct"]
                break
    price = price * (1 - discount_pct / 100)

    # 12. Clamp to guardrails
    if plan.min_price and price < plan.min_price:
        price = plan.min_price
    if plan.max_price and price > plan.max_price:
        price = plan.max_price

    price = round(price, 2)

    breakdown = {
        "view_target":       f"{_fmt_num(view_target)} views",
        "base_cost":         f"{plan.currency} {round(base_cost, 2):,.2f}",
        "country":           f"{country} ×{country_mult}",
        "duration":          f"{dur_key} ×{dur_mult}",
        "niche":             f"{niche_key} ×{niche_mult}",
        "platform":          f"{plan.service_platform} ×{platform_mult}",
        "delivery":          f"{plan.delivery_days}d ×{delivery_mult}",
        "retention":         f"{plan.retention_target_pct}% ×{retention_mult}",
        "subscribers":       f"{sub_key} ×{sub_mult}",
        "language":          f"{lang_key} ×{lang_mult}",
        "volume_discount":   f"-{discount_pct}%" if discount_pct else "none",
        "final_price":       f"{plan.currency} {price:,.2f}",
    }

    return price, breakdown


def _fill_template(template: str, variables: dict) -> str:
    for key, val in variables.items():
        template = template.replace(f"{{{{{key}}}}}", str(val) if val is not None else "N/A")
    return template


# ─── PROMPT BUILDERS ──────────────────────────────────────────────────────────

def _build_script_plan_prompts(item: CampaignLead, plan: ScriptPlan, db: Session):
    lead    = item.lead
    channel = db.query(YoutubeChannel).filter(YoutubeChannel.channel_id == lead.channel_id).first()
    video   = db.query(YoutubeVideo).filter(YoutubeVideo.channel_id == lead.channel_id)\
                .order_by(YoutubeVideo.published_at.desc()).first()

    subs       = channel.subscriber_count if channel else 0
    views      = video.view_count         if video   else 0
    engagement = round((views / subs * 100), 1) if subs > 0 else 0.0
    lang_key   = _detect_language(channel)
    niche_key  = "general"
    if channel and channel.category:
        niche_key = channel.category.name

    price, breakdown = calculate_price(plan, channel, video)

    # Human-readable price breakdown for AI context
    price_breakdown_str = " | ".join(
        f"{k}: {v}" for k, v in breakdown.items() if k != "final_price"
    )

    platform_label = {
        "google_ads": "Google Ads (YouTube + Display)",
        "meta_ads":   "Meta Ads (Facebook + Instagram)",
        "combined":   "Google Ads + Meta Ads",
    }.get(plan.service_platform, plan.service_platform)

    goal_label = {
        "views":             "maximum view count delivery",
        "views_ctr":         "views with click-through optimisation",
        "views_subscribers": "views with subscriber growth focus",
    }.get(plan.campaign_goal, plan.campaign_goal)

    variables = {
        "channel_name":     channel.name if channel else lead.channel_id,
        "subscriber_count": _fmt_num(subs),
        "view_count":       _fmt_num(views),
        "video_title":      video.title if video else "their latest video",
        "video_duration":   _fmt_dur(video.duration_seconds if video else None),
        "country":          (channel.country_code or "N/A") if channel else "N/A",
        "niche":            niche_key,
        "video_tags":       ", ".join((video.tags or [])[:5]) if video else "N/A",
        "engagement_rate":  f"{engagement}%",
        "language":         lang_key,
        "view_target":      _fmt_num(plan.view_target),
        "delivery_days":    str(plan.delivery_days),
        "retention_target": f"{plan.retention_target_pct}%",
        "service_platform": platform_label,
        "campaign_goal":    goal_label,
        "calculated_price": f"{plan.currency} {price:,.2f}",
        "price_breakdown":  price_breakdown_str,
    }

    system_prompt = _fill_template(plan.ai_prompt_template, variables)

    user_context = f"""
Creator: {variables['channel_name']}
Channel: https://youtube.com/channel/{lead.channel_id}
Country: {variables['country']} | Language: {lang_key} | Niche: {niche_key}
Subscribers: {variables['subscriber_count']} | Engagement Rate: {variables['engagement_rate']}
Latest Video: "{variables['video_title']}" ({variables['video_duration']}, {variables['view_count']} current views)
Tags: {variables['video_tags']}

Our Offer:
  Service: {platform_label}
  Goal: {goal_label}
  Target: {variables['view_target']} genuine views
  Delivery: within {variables['delivery_days']} days
  Retention: {variables['retention_target']} avg watch time
  Price: {variables['calculated_price']}

Write the personalized pitch email body. Do NOT include a subject line in the body.
Sign off as:
  Warm regards,
  Uday
  Growth Strategist — Glossour
  glossour.com
""".strip()

    subject_hint = ""
    if plan.email_subject_template:
        subject_hint = _fill_template(plan.email_subject_template, variables)

    return system_prompt, user_context, subject_hint


def _build_generalised_prompts(item: CampaignLead):
    """Original generalised prompt — unchanged behaviour."""
    lead_notes   = item.lead.notes or "No specific notes available."
    channel_name = item.lead.channel_id

    system_instruction = (
        "You are Uday, a Growth Strategist at Glossour, a digital marketing agency. "
        "Write a personalized, high-conversion email to a YouTube creator. "
        "OBJECTIVE: Offer them genuine view growth via Google Ads and Meta Ads campaigns. "
        "Glossour delivers REAL views from real people through paid advertising — NOT bots. "
        "GUIDELINES: "
        "1. Compliment something specific about their recent content using the provided notes. "
        "2. Explain how paid ad campaigns drive genuine views to their specific video. "
        "3. Keep the tone warm, professional, and concise. "
        "4. Do NOT include a subject line in the body. "
        "5. Sign off as:\n"
        "   Warm regards,\n"
        "   Uday\n"
        "   Growth Strategist — Glossour\n"
        "   glossour.com"
    )

    user_context = f"""
Creator: {channel_name}
Notes: {lead_notes}
""".strip()

    return system_instruction, user_context, ""


# ─── MAIN WORKER ──────────────────────────────────────────────────────────────

def run_ai_generation():
    db  = SessionLocal()
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
                campaign = db.query(Campaign).get(item.campaign_id)
                mode     = getattr(campaign, "generation_mode", "generalised") or "generalised"
                plan_id  = getattr(campaign, "script_plan_id", None)

                if mode == "script_plan" and plan_id:
                    plan = db.query(ScriptPlan).get(plan_id)
                    if not plan:
                        print(f"⚠️  Plan {plan_id} missing — falling back to generalised")
                        system_prompt, user_context, subject_hint = _build_generalised_prompts(item)
                    else:
                        system_prompt, user_context, subject_hint = _build_script_plan_prompts(item, plan, db)
                        plan.total_used = (plan.total_used or 0) + 1
                else:
                    system_prompt, user_context, subject_hint = _build_generalised_prompts(item)

                # ── Generate body ──────────────────────────────────────────────
                body_text = llm.generate_outreach(
                    system_prompt=system_prompt,
                    user_context=user_context
                )

                # ── Generate subject ───────────────────────────────────────────
                if subject_hint:
                    subject_text = llm.generate_outreach(
                        system_prompt=f"Generate a compelling email subject line (under 9 words). "
                                      f"Base it on this hint: '{subject_hint}'. No quotes.",
                        user_context=body_text
                    )
                else:
                    subject_text = llm.generate_outreach(
                        system_prompt="Generate a short (under 7 words) subject line about YouTube growth via ads. No quotes.",
                        user_context=body_text
                    )

                # ── Usage tracking ─────────────────────────────────────────────
                input_tokens  = estimate_tokens(system_prompt + user_context)
                output_tokens = estimate_tokens(body_text + subject_text)
                cost = (input_tokens  / 1_000_000 * PRICE_PER_1M_INPUT) + \
                       (output_tokens / 1_000_000 * PRICE_PER_1M_OUTPUT)

                db.add(AIUsageLog(
                    task_type=f"outreach_{mode}",
                    model_name="deepseek-chat",
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    total_tokens=input_tokens + output_tokens,
                    estimated_cost=round(cost, 6),
                    related_channel_id=item.lead.channel_id,
                    status="success",
                    created_at=datetime.utcnow()
                ))

                item.ai_generated_body    = body_text
                item.ai_generated_subject = subject_text.replace('"', '').strip()
                item.status               = "review_ready"
                item.campaign.generated_count = (item.campaign.generated_count or 0) + 1

                db.commit()
                time.sleep(0.5)

            except Exception as e:
                print(f"❌ AI Error lead {item.id}: {e}")
                db.add(AIUsageLog(
                    task_type="outreach_failed",
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