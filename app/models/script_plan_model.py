from sqlalchemy import Column, Integer, String, Text, Float, BigInteger, TIMESTAMP, JSON
from datetime import datetime
from app.core.database import Base


class ScriptPlan(Base):
    """
    A view-delivery pricing package offered to YouTube creators.

    Glossour sells GENUINE YouTube views via Google Ads + Meta Ads.
    Each plan defines how to CALCULATE the price for a specific creator
    based on their video's country, duration, niche, and other signals.

    Price Formula:
        final = (view_target / 1000) × base_price_per_1k
                × country_mult
                × duration_mult
                × niche_mult
                × platform_mult
                × retention_mult
                × delivery_mult
                × volume_discount
        clamped between min_price and max_price
    """
    __tablename__ = "script_plans"

    id = Column(Integer, primary_key=True, index=True)

    # ── Identity ──────────────────────────────────────────────────────────────
    name        = Column(String, nullable=False)    # "1M Views — Standard Package"
    description = Column(Text, nullable=True)
    status      = Column(String, default="active")  # active | draft | archived
    color_tag   = Column(String, default="orange")  # orange | blue | green | red | violet

    # ── What We're Selling ────────────────────────────────────────────────────
    service_platform = Column(String, default="combined")
    # google_ads  — YouTube/Google Display only
    # meta_ads    — Facebook + Instagram only
    # combined    — Google Ads + Meta Ads together (premium)

    campaign_goal = Column(String, default="views")
    # views               — pure view count delivery
    # views_ctr           — views + click-through optimisation
    # views_subscribers   — views + subscriber growth focus

    # ── View Package ─────────────────────────────────────────────────────────
    view_target      = Column(BigInteger, default=1_000_000)  # e.g. 1000000 = 1M views
    base_price_per_1k = Column(Float, nullable=False)          # e.g. 1.50 = $1.50 per 1k views

    currency = Column(String(5), default="USD")

    # ── Country Pricing (JSON map: ISO code → multiplier) ─────────────────────
    # Example: {"US": 2.8, "GB": 2.2, "AU": 2.5, "CA": 2.3,
    #            "DE": 1.8, "FR": 1.6, "IN": 0.6, "PK": 0.5,
    #            "PH": 0.55, "BR": 0.9, "MX": 0.85, "default": 1.0}
    country_multipliers = Column(JSON, nullable=True)

    # ── Duration Multipliers (JSON) ───────────────────────────────────────────
    # Keyed by duration bucket:
    # shorts   = < 60 seconds   (YouTube Shorts — special ad format)
    # short    = 1–5 minutes    (pre-roll only)
    # mid      = 5–15 minutes   (pre + mid-roll)
    # long     = 15–60 minutes  (multiple ad placements)
    # ultra    = 60+ minutes    (expensive, hard to retain)
    # Example: {"shorts": 0.65, "short": 0.9, "mid": 1.0, "long": 1.25, "ultra": 1.5}
    duration_multipliers = Column(JSON, nullable=True)

    # ── Niche / Category Multipliers (JSON) ───────────────────────────────────
    # Reflects advertiser CPM by content vertical.
    # Example: {"finance": 1.6, "crypto": 1.7, "tech": 1.3,
    #            "business": 1.4, "education": 1.1, "gaming": 1.0,
    #            "lifestyle": 0.9, "entertainment": 0.85, "food": 0.95,
    #            "fitness": 1.0, "travel": 0.95, "default": 1.0}
    niche_multipliers = Column(JSON, nullable=True)

    # ── Platform Multiplier ───────────────────────────────────────────────────
    # google_ads only = 1.0 (base)
    # meta_ads only   = 0.9 (slightly cheaper, YouTube views via Meta)
    # combined        = 1.2 (both platforms, better reach)
    platform_multiplier = Column(Float, default=1.0)

    # ── Delivery Speed ────────────────────────────────────────────────────────
    delivery_days       = Column(Integer, default=30)   # promised delivery window
    delivery_multiplier = Column(Float, default=1.0)
    # express (7d)  = 1.35  (rush premium)
    # standard (30d)= 1.0
    # slow_burn (90d)= 0.82 (more organic-looking growth, cheaper)

    # ── Retention Target ─────────────────────────────────────────────────────
    retention_target_pct  = Column(Integer, default=30) # avg watch time % target
    retention_multiplier  = Column(Float, default=1.0)
    # basic   (15-25%) = 1.0
    # standard(30-40%) = 1.2
    # high    (50%+)   = 1.5  — needs precise audience match, costly

    # ── Subscriber Count Multiplier ───────────────────────────────────────────
    # Smaller channels are harder to run ads for (less trust signal)
    # JSON: {"tiny": 1.15, "small": 1.05, "mid": 1.0, "large": 0.95, "mega": 0.90}
    # tiny  = <10k, small = 10k-100k, mid = 100k-1M, large = 1M-5M, mega = 5M+
    subscriber_multipliers = Column(JSON, nullable=True)

    # ── Language Multiplier ───────────────────────────────────────────────────
    # English audience = most expensive targeting
    # Example: {"en": 1.0, "hi": 0.65, "es": 0.80, "pt": 0.75, "default": 0.85}
    language_multipliers = Column(JSON, nullable=True)

    # ── Volume Discounts (JSON list, sorted by threshold) ─────────────────────
    # Applied to the total order when buying a large view package
    # Example: [
    #   {"threshold": 500000,   "discount_pct": 5},
    #   {"threshold": 1000000,  "discount_pct": 10},
    #   {"threshold": 5000000,  "discount_pct": 15},
    #   {"threshold": 10000000, "discount_pct": 20}
    # ]
    volume_discounts = Column(JSON, nullable=True)

    # ── Price Guardrails ──────────────────────────────────────────────────────
    min_price = Column(Float, nullable=True)   # floor — never quote below this
    max_price = Column(Float, nullable=True)   # ceiling — never quote above this

    # ── AI Prompt Template ────────────────────────────────────────────────────
    # Available variables (filled from real lead data before calling DeepSeek):
    #   {{channel_name}}, {{subscriber_count}}, {{video_title}}, {{view_count}},
    #   {{video_duration}}, {{country}}, {{niche}}, {{video_tags}},
    #   {{engagement_rate}}, {{language}},
    #   {{view_target}}, {{delivery_days}}, {{retention_target}},
    #   {{service_platform}}, {{campaign_goal}},
    #   {{calculated_price}}, {{price_breakdown}}
    ai_prompt_template     = Column(Text, nullable=False)
    email_subject_template = Column(String, nullable=True)

    # ── Stats ─────────────────────────────────────────────────────────────────
    total_used = Column(Integer, default=0)

    created_at = Column(TIMESTAMP, default=datetime.utcnow)
    updated_at = Column(TIMESTAMP, default=datetime.utcnow, onupdate=datetime.utcnow)