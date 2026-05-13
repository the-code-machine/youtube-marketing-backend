"""
app/workers/campaign/ai_generator.py

Fix: Removed AIUsageLog(campaign_lead_id=...) which crashed every lead.
     AIUsageLog model doesn't have a campaign_lead_id field.
     Usage tracking wrapped in try/except so it never blocks generation.
"""

import os
os.environ["GLOSSOUR_WORKER_MODE"] = "true"

import logging
from datetime import datetime

from sqlalchemy.orm import Session
from sqlalchemy import desc

from app.core.database import SessionLocal
from app.models.campaign import Campaign, CampaignLead
from app.models.script_plan_model import ScriptPlan
from app.models.youtube_channel import YoutubeChannel
from app.models.youtube_video import YoutubeVideo
from app.services.llm_service import LLMService

logger = logging.getLogger(__name__)

# Try to import AIUsageLog — if it fails or has different fields, just skip logging
try:
    from app.models.ai_usage import AIUsageLog
    _HAS_AI_USAGE_LOG = True
except ImportError:
    _HAS_AI_USAGE_LOG = False
    logger.warning("AIUsageLog model not found — usage tracking disabled")


# ─── FORMATTERS ───────────────────────────────────────────────────────────────

def _fmt_num(n) -> str:
    if not n: return "0"
    n = int(n)
    if n >= 1_000_000: return f"{n/1_000_000:.1f}M"
    if n >= 1_000:     return f"{n/1_000:.0f}k"
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
    if not sec: return "mid"
    sec = int(sec)
    if sec < 60:   return "shorts"
    if sec < 300:  return "short"
    if sec < 900:  return "mid"
    if sec < 3600: return "long"
    return "ultra"


def _sub_bucket(subs) -> str:
    if not subs: return "small"
    subs = int(subs)
    if subs < 10_000:    return "tiny"
    if subs < 100_000:   return "small"
    if subs < 1_000_000: return "mid"
    if subs < 5_000_000: return "large"
    return "mega"


def _detect_language(channel) -> str:
    english_countries    = {"US", "GB", "AU", "CA", "NZ", "IE"}
    hindi_countries      = {"IN", "NP"}
    spanish_countries    = {"ES", "MX", "AR", "CO", "CL", "PE"}
    portuguese_countries = {"BR", "PT"}
    cc = (channel.country_code or "").upper() if channel else ""
    if cc in english_countries:    return "en"
    if cc in hindi_countries:      return "hi"
    if cc in spanish_countries:    return "es"
    if cc in portuguese_countries: return "pt"
    return "default"


# ─── INLINE PRICING ENGINE ────────────────────────────────────────────────────

DEFAULT_COUNTRY = {
    "US": 2.8, "GB": 2.2, "AU": 2.5, "CA": 2.3, "DE": 1.8, "FR": 1.6,
    "SG": 1.5, "JP": 1.7, "AE": 1.4, "NL": 1.6,
    "BR": 0.9, "MX": 0.85, "ID": 0.7, "PH": 0.55,
    "IN": 0.6, "PK": 0.5, "BD": 0.45, "NG": 0.5,
    "default": 1.0,
}
DEFAULT_DURATION = {"shorts": 0.65, "short": 0.9, "mid": 1.0, "long": 1.25, "ultra": 1.5}
DEFAULT_NICHE    = {
    "finance": 1.6, "crypto": 1.7, "tech": 1.3, "business": 1.4,
    "education": 1.1, "gaming": 1.0, "lifestyle": 0.9,
    "entertainment": 0.85, "food": 0.95, "fitness": 1.0, "travel": 0.95,
    "default": 1.0,
}
DEFAULT_SUBS = {"tiny": 1.15, "small": 1.05, "mid": 1.0, "large": 0.95, "mega": 0.9}
DEFAULT_LANG = {"en": 1.0, "hi": 0.65, "es": 0.8, "pt": 0.75, "default": 0.85}


def calculate_price(plan, channel, video) -> tuple:
    view_target  = plan.view_target or 1_000_000
    base_per_1k  = plan.base_price_per_1k or 1.0

    country_mults = plan.country_multipliers    or DEFAULT_COUNTRY
    dur_mults     = plan.duration_multipliers   or DEFAULT_DURATION
    niche_mults   = plan.niche_multipliers      or DEFAULT_NICHE
    sub_mults     = plan.subscriber_multipliers or DEFAULT_SUBS
    lang_mults    = plan.language_multipliers   or DEFAULT_LANG

    country_key = (channel.country_code or "default").upper() if channel else "default"
    dur_key     = _dur_bucket(video.duration_seconds if video else None)
    niche_key   = "default"
    if channel and getattr(channel, "category", None):
        niche_key = channel.category.name.lower() if hasattr(channel.category, "name") else "default"
    sub_key  = _sub_bucket(channel.subscriber_count if channel else None)
    lang_key = _detect_language(channel)

    country_mult   = country_mults.get(country_key, country_mults.get("default", 1.0))
    dur_mult       = dur_mults.get(dur_key, 1.0)
    niche_mult     = niche_mults.get(niche_key, niche_mults.get("default", 1.0))
    sub_mult       = sub_mults.get(sub_key, 1.0)
    lang_mult      = lang_mults.get(lang_key, lang_mults.get("default", 0.85))
    platform_mult  = plan.platform_multiplier  or 1.0
    delivery_mult  = plan.delivery_multiplier  or 1.0
    retention_mult = plan.retention_multiplier or 1.0

    base_cost = (view_target / 1000) * base_per_1k
    price = (
        base_cost
        * country_mult * dur_mult * niche_mult * sub_mult * lang_mult
        * platform_mult * delivery_mult * retention_mult
    )

    discount_pct = 0
    if plan.volume_discounts:
        for tier in sorted(plan.volume_discounts, key=lambda x: x["threshold"], reverse=True):
            if view_target >= tier["threshold"]:
                discount_pct = tier["discount_pct"]
                break
    price = price * (1 - discount_pct / 100)

    if plan.min_price and price < plan.min_price:
        price = plan.min_price
    if plan.max_price and price > plan.max_price:
        price = plan.max_price

    return round(price, 2), {}


def _fill_template(template: str, variables: dict) -> str:
    for key, val in variables.items():
        template = template.replace(f"{{{{{key}}}}}", str(val) if val is not None else "N/A")
    return template


# ─── PROMPT BUILDERS ──────────────────────────────────────────────────────────

def _build_generalised_prompts(item: CampaignLead, db: Session):
    lead = item.lead

    channel = (
        db.query(YoutubeChannel)
        .filter(YoutubeChannel.channel_id == lead.channel_id)
        .first()
    )
    video = (
        db.query(YoutubeVideo)
        .filter(YoutubeVideo.channel_id == lead.channel_id)
        .order_by(desc(YoutubeVideo.published_at))
        .first()
    )

    channel_name = (channel.name if channel else None) or lead.channel_id
    subs_fmt     = _fmt_num(channel.subscriber_count if channel else 0)
    video_title  = video.title if video else "your recent video"
    view_count   = _fmt_num(video.view_count if video else 0)
    niche        = "content"
    if channel and getattr(channel, "category", None):
        niche = channel.category.name if hasattr(channel.category, "name") else "content"
    language     = _detect_language(channel)
    country      = (channel.country_code or "").upper() if channel else ""
    extra_notes  = lead.notes or ""

    system_instruction = (
        "You are Uday, Growth Strategist at Glossour (glossour.com). "
        "Glossour drives REAL YouTube views via Google Ads & Meta Ads — not bots.\n\n"
        "Write a cold outreach email to the YouTube creator below.\n\n"
        "HARD RULES:\n"
        "  • Under 120 words total\n"
        "  • DO NOT put a subject line inside the body\n"
        "  • DO NOT open with 'I came across your channel'\n"
        "  • DO NOT use hollow words like 'amazing', 'incredible'\n\n"
        "STRUCTURE:\n"
        "  1. Opening — 1 specific compliment using the actual video title\n"
        "  2. Problem — 1 sentence on the pain: views plateau despite good content\n"
        "  3. Offer — what Glossour does + one concrete result number\n"
        "  4. CTA — 'Just reply YES and I'll send you a free campaign preview'\n"
        "  5. Sign-off:\n"
        "       Warm regards,\n"
        "       Uday\n"
        "       Growth Strategist — Glossour\n"
        "       glossour.com\n"
        "  6. P.S. — one urgency line\n\n"
        "TONE: Warm, direct, peer-to-peer. NOT salesy."
    )

    user_context = f"""
Creator Name: {channel_name}
Channel ID: {lead.channel_id}
Subscribers: {subs_fmt}
Latest Video Title: "{video_title}"
Latest Video Views: {view_count}
Niche: {niche}
Language: {language}
Country: {country if country else 'Unknown'}
Extra Notes: {extra_notes if extra_notes else 'None'}
""".strip()

    subject_hint = (
        f"Write a short cold-email subject for creator '{channel_name}' "
        f"about growing views for '{video_title}'. "
        f"Under 8 words, no hype words, no question marks."
    )

    return system_instruction, user_context, subject_hint


def _build_script_plan_prompts(item: CampaignLead, plan, db: Session):
    lead    = item.lead
    channel = db.query(YoutubeChannel).filter(YoutubeChannel.channel_id == lead.channel_id).first()
    video   = (
        db.query(YoutubeVideo)
        .filter(YoutubeVideo.channel_id == lead.channel_id)
        .order_by(desc(YoutubeVideo.published_at))
        .first()
    )

    subs       = channel.subscriber_count if channel else 0
    views      = video.view_count         if video   else 0
    engagement = round((views / subs * 100), 1) if subs > 0 else 0.0
    lang_key   = _detect_language(channel)
    niche_key  = "general"
    if channel and getattr(channel, "category", None):
        niche_key = channel.category.name if hasattr(channel.category, "name") else "general"

    price, _ = calculate_price(plan, channel, video)

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
    }

    system_prompt = _fill_template(plan.ai_prompt_template, variables)
    user_context  = f"Creator: {variables['channel_name']}\nOffer: {platform_label} — {variables['calculated_price']}"
    subject_hint  = _fill_template(plan.email_subject_template, variables) if plan.email_subject_template else ""

    return system_prompt, user_context, subject_hint


# ─── USAGE LOGGING (safe — never crashes generation) ─────────────────────────

def _log_usage(db: Session, item_id: int, input_tokens: int, output_tokens: int):
    if not _HAS_AI_USAGE_LOG:
        return
    try:
        # Try common field names — if they fail, silently skip
        log = AIUsageLog(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            estimated_cost=round(
                (input_tokens / 1_000_000) * 0.14 + (output_tokens / 1_000_000) * 0.28, 6
            ),
        )
        db.add(log)
        db.flush()
    except Exception as e:
        logger.debug(f"AIUsageLog skipped: {e}")
        db.rollback()


# ─── MAIN WORKER ──────────────────────────────────────────────────────────────

def run_ai_generation():
    db  = SessionLocal()
    llm = LLMService()

    try:
        queue = (
            db.query(CampaignLead)
            .filter(CampaignLead.status == "queued")
            .limit(10)
            .all()
        )

        if not queue:
            logger.info("AI generator: no queued leads.")
            return

        logger.info(f"🤖 Generating AI drafts for {len(queue)} leads...")

        for item in queue:
            try:
                campaign = db.query(Campaign).get(item.campaign_id)
                mode     = getattr(campaign, "generation_mode", "generalised") or "generalised"
                plan_id  = getattr(campaign, "script_plan_id", None)

                if mode == "script_plan" and plan_id:
                    plan = db.query(ScriptPlan).get(plan_id)
                    if not plan:
                        system_prompt, user_context, subject_hint = _build_generalised_prompts(item, db)
                    else:
                        system_prompt, user_context, subject_hint = _build_script_plan_prompts(item, plan, db)
                        plan.total_used = (plan.total_used or 0) + 1
                else:
                    system_prompt, user_context, subject_hint = _build_generalised_prompts(item, db)

                # ── Generate body ──────────────────────────────────────────
                body_text = llm.generate_outreach(
                    system_prompt=system_prompt,
                    user_context=user_context,
                )

                # ── Generate subject ───────────────────────────────────────
                subject_text = None
                if subject_hint:
                    subject_text = llm.generate_outreach(
                        system_prompt=(
                            "Generate a compelling cold-email subject line. "
                            "Under 9 words, no hype words, reference the creator specifically. "
                            "Return ONLY the subject line — no quotes, no extra text."
                        ),
                        user_context=subject_hint,
                    )

                item.ai_generated_body    = body_text
                item.ai_generated_subject = subject_text
                item.status               = "review_ready"

                # ── Log usage safely ───────────────────────────────────────
                input_tokens  = (len(system_prompt) + len(user_context)) // 4
                output_tokens = len(body_text or "") // 4
                _log_usage(db, item.id, input_tokens, output_tokens)

                db.commit()
                logger.info(f"✅ Generated draft for lead {item.id}")

            except Exception as e:
                logger.error(f"❌ Error for lead {item.id}: {e}", exc_info=True)
                item.status = "failed"
                item.error_message = str(e)[:500]
                db.commit()

    except Exception as e:
        logger.error(f"AI generator crashed: {e}", exc_info=True)
    finally:
        db.close()


if __name__ == "__main__":
    run_ai_generation()