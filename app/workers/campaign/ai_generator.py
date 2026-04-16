"""
app/workers/campaign/ai_generator.py

Fixes vs previous version:
  - Removed wrong `from app.services.pricing_service import calculate_price`
  - calculate_price() stays inline (as it was originally)
  - _build_generalised_prompts now accepts `db` and pulls real channel + video data
  - run_ai_generation passes `db` into _build_generalised_prompts
  - All other imports match the original file exactly
"""

import time
from datetime import datetime

from sqlalchemy.orm import Session
from sqlalchemy import desc

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


# ─── PRICING ENGINE (inline — no external service) ────────────────────────────

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


def calculate_price(plan: ScriptPlan, channel, video) -> tuple:
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

    country_mult  = country_mults.get(country_key, country_mults.get("default", 1.0))
    dur_mult      = dur_mults.get(dur_key, 1.0)
    niche_mult    = niche_mults.get(niche_key, niche_mults.get("default", 1.0))
    sub_mult      = sub_mults.get(sub_key, 1.0)
    lang_mult     = lang_mults.get(lang_key, lang_mults.get("default", 0.85))
    platform_mult = plan.platform_multiplier  or 1.0
    delivery_mult = plan.delivery_multiplier  or 1.0
    retention_mult= plan.retention_multiplier or 1.0

    base_cost = (view_target / 1000) * base_per_1k
    price     = (
        base_cost
        * country_mult * dur_mult * niche_mult * sub_mult * lang_mult
        * platform_mult * delivery_mult * retention_mult
    )

    # Volume discount
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

    price = round(price, 2)

    breakdown = {
        "view_target":     f"{_fmt_num(view_target)} views",
        "base_cost":       f"{plan.currency} {round(base_cost, 2):,.2f}",
        "country":         f"{country_key} ×{country_mult}",
        "duration":        f"{dur_key} ×{dur_mult}",
        "niche":           f"{niche_key} ×{niche_mult}",
        "platform":        f"{plan.service_platform} ×{platform_mult}",
        "delivery":        f"{plan.delivery_days}d ×{delivery_mult}",
        "retention":       f"{plan.retention_target_pct}% ×{retention_mult}",
        "subscribers":     f"{sub_key} ×{sub_mult}",
        "language":        f"{lang_key} ×{lang_mult}",
        "volume_discount": f"-{discount_pct}%" if discount_pct else "none",
        "final_price":     f"{plan.currency} {price:,.2f}",
    }

    return price, breakdown


def _fill_template(template: str, variables: dict) -> str:
    for key, val in variables.items():
        template = template.replace(f"{{{{{key}}}}}", str(val) if val is not None else "N/A")
    return template


# ─── PROMPT BUILDERS ──────────────────────────────────────────────────────────

def _build_generalised_prompts(item: CampaignLead, db: Session):
    """
    Personalised prompt using real channel + video data from DB.
    Previously this used only `lead.notes` (almost always null) and
    `lead.channel_id` as the channel name — now it fetches the real data.
    """
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
    subs         = channel.subscriber_count if channel else 0
    subs_fmt     = _fmt_num(subs)
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
        "Glossour drives REAL YouTube views via Google Ads & Meta Ads — not bots. "
        "\n\n"
        "Write a cold outreach email to the YouTube creator below.\n\n"
        "HARD RULES:\n"
        "  • Under 120 words total\n"
        "  • DO NOT put a subject line inside the body\n"
        "  • DO NOT open with 'I came across your channel' or 'I stumbled upon'\n"
        "  • DO NOT use hollow words like 'amazing', 'incredible', 'love your work'\n"
        "\n"
        "STRUCTURE (exactly in this order):\n"
        "  1. Opening — 1 specific compliment that uses the actual video title "
        "or subscriber milestone to prove you did your homework.\n"
        "  2. Problem — 1 sentence on the pain: views plateau despite good content.\n"
        "  3. Offer — what Glossour does + one concrete result number "
        "(e.g. '50,000–200,000 real views in 14 days via paid ads').\n"
        "  4. CTA — ultra-low friction: 'Just reply YES and I'll send you a free "
        "campaign preview for your channel.'\n"
        "  5. Sign-off:\n"
        "       Warm regards,\n"
        "       Uday\n"
        "       Growth Strategist — Glossour\n"
        "       glossour.com\n"
        "  6. P.S. — one urgency line "
        "(e.g. 'We only onboard 5 new creators per week to keep quality high.').\n"
        "\n"
        "TONE: Warm, direct, peer-to-peer. NOT salesy."
    )

    user_context = f"""
Creator Name: {channel_name}
Channel ID: {lead.channel_id}
Channel URL: https://youtube.com/channel/{lead.channel_id}
Subscribers: {subs_fmt}
Latest Video Title: "{video_title}"
Latest Video Views: {view_count}
Niche / Category: {niche}
Primary Language: {language}
Country: {country if country else 'Unknown'}
Extra Notes: {extra_notes if extra_notes else 'None'}
""".strip()

    # Subject hint returned — used to generate a channel-specific subject line
    subject_hint = (
        f"Write a short, specific cold-email subject line for creator '{channel_name}' "
        f"about growing views for their video '{video_title}'. "
        f"Under 8 words, no hype words (amazing/incredible/opportunity), no question marks."
    )

    return system_instruction, user_context, subject_hint


def _build_script_plan_prompts(item: CampaignLead, plan: ScriptPlan, db: Session):
    """Script-plan based prompt — unchanged from original."""
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

    price, breakdown = calculate_price(plan, channel, video)
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

Write the personalised pitch email body. Do NOT include a subject line in the body.
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


# ─── MAIN WORKER ──────────────────────────────────────────────────────────────

PRICE_PER_1M_INPUT  = 0.14
PRICE_PER_1M_OUTPUT = 0.28


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
                        system_prompt, user_context, subject_hint = _build_generalised_prompts(item, db)
                    else:
                        system_prompt, user_context, subject_hint = _build_script_plan_prompts(item, plan, db)
                        plan.total_used = (plan.total_used or 0) + 1
                else:
                    # ← db is now passed so real channel/video data is used
                    system_prompt, user_context, subject_hint = _build_generalised_prompts(item, db)

                # ── Generate body ──────────────────────────────────────────────
                body_text = llm.generate_outreach(
                    system_prompt=system_prompt,
                    user_context=user_context,
                )

                # ── Generate subject ───────────────────────────────────────────
                if subject_hint:
                    subject_text = llm.generate_outreach(
                        system_prompt=(
                            "Generate a compelling cold-email subject line. "
                            "Rules: under 9 words, NO hype words (amazing/incredible/opportunity), "
                            "reference the creator or their content specifically. "
                            "Return ONLY the subject line — no quotes, no extra text."
                        ),
                        user_context=subject_hint,
                    )
                else:
                    subject_text = None

                item.ai_generated_body    = body_text
                item.ai_generated_subject = subject_text
                item.status               = "review_ready"

                # ── Log AI usage ───────────────────────────────────────────────
                input_tokens  = (len(system_prompt) + len(user_context)) // 4
                output_tokens = len(body_text or "") // 4
                cost = (
                    (input_tokens  / 1_000_000) * PRICE_PER_1M_INPUT
                    + (output_tokens / 1_000_000) * PRICE_PER_1M_OUTPUT
                )

                db.add(AIUsageLog(
                    campaign_lead_id=item.id,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    estimated_cost=cost,
                ))
                db.commit()

                print(f"✅ Generated draft for lead {item.id} | ~${cost:.5f}")

            except Exception as e:
                print(f"❌ Error for lead {item.id}: {e}")
                item.status = "failed"
                item.error_message = str(e)
                db.commit()

    finally:
        db.close()