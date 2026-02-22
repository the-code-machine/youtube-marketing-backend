from sqlalchemy import Column, Integer, String, Text, Float, BigInteger, TIMESTAMP
from sqlalchemy.dialects.postgresql import ARRAY
from datetime import datetime
from app.core.database import Base


class ScriptPlan(Base):
    """
    Reusable AI prompt templates tied to specific deal/pricing structures.
    When a campaign is created with generation_mode='script_plan', the AI
    worker uses the selected plan's filled prompt instead of the default prompt.

    Variables the generator injects before calling the LLM:
        {{channel_name}}, {{subscriber_count}}, {{view_count}}, {{video_title}},
        {{video_duration}}, {{country}}, {{video_tags}}, {{calculated_price}},
        {{engagement_rate}}, {{service_type}}, {{pitch_angle}}
    """
    __tablename__ = "script_plans"

    id = Column(Integer, primary_key=True, index=True)

    name        = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    status      = Column(String, default="active")   # active | draft | archived
    color_tag   = Column(String, default="blue")      # blue | green | amber | pink | violet

    service_type = Column(String, nullable=False)
    # sponsored_mention | dedicated_video | affiliate_deal | product_review | shoutout

    pitch_angle = Column(String, nullable=True)
    # views_based | engagement_hook | niche_authority | viral_potential | trust_builder

    # Pricing — passed into prompt as {{calculated_price}}
    pricing_model     = Column(String, default="flat_rate")
    base_price        = Column(Float, nullable=True)
    price_per_view    = Column(Float, nullable=True)
    price_per_1k      = Column(Float, nullable=True)
    revenue_share_pct = Column(Float, nullable=True)
    currency          = Column(String(5), default="USD")
    min_guarantee     = Column(Float, nullable=True)

    # Targeting (display / matching only)
    min_views        = Column(BigInteger, nullable=True)
    max_views        = Column(BigInteger, nullable=True)
    min_subscribers  = Column(Integer, nullable=True)
    max_subscribers  = Column(Integer, nullable=True)
    min_duration_sec = Column(Integer, nullable=True)
    max_duration_sec = Column(Integer, nullable=True)
    target_countries = Column(ARRAY(String), nullable=True)

    ai_prompt_template     = Column(Text, nullable=False)
    email_subject_template = Column(String, nullable=True)

    total_used = Column(Integer, default=0)

    created_at = Column(TIMESTAMP, default=datetime.utcnow)
    updated_at = Column(TIMESTAMP, default=datetime.utcnow, onupdate=datetime.utcnow)