
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import List, Optional, Dict, Any
from datetime import datetime

from app.core.database import SessionLocal
from app.models.script_plan_model import ScriptPlan

router = APIRouter(prefix="/api/script-plans", tags=["Script Engine"])


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ─── Pydantic Schemas ─────────────────────────────────────────────────────────

class VolumeDiscount(BaseModel):
    threshold:    int
    discount_pct: float


class PlanBase(BaseModel):
    # Identity
    name:        str
    description: Optional[str] = None
    status:      str = "active"
    color_tag:   str = "orange"

    # Package
    service_platform: str = "combined"  # google_ads | meta_ads | combined
    campaign_goal:    str = "views"     # views | views_ctr | views_subscribers
    view_target:      int = 1_000_000
    base_price_per_1k: float
    currency:         str = "USD"

    # Multipliers (JSON dicts)
    country_multipliers:    Optional[Dict[str, float]] = None
    duration_multipliers:   Optional[Dict[str, float]] = None
    niche_multipliers:      Optional[Dict[str, float]] = None
    subscriber_multipliers: Optional[Dict[str, float]] = None
    language_multipliers:   Optional[Dict[str, float]] = None

    # Platform multiplier (scalar — set automatically from service_platform)
    platform_multiplier: float = 1.0

    # Delivery
    delivery_days:       int   = 30
    delivery_multiplier: float = 1.0

    # Retention
    retention_target_pct:  int   = 30
    retention_multiplier:  float = 1.0

    # Volume discounts
    volume_discounts: Optional[List[Dict[str, Any]]] = None

    # Guardrails
    min_price: Optional[float] = None
    max_price: Optional[float] = None

    # AI
    ai_prompt_template:     str
    email_subject_template: Optional[str] = None


class PlanUpdate(BaseModel):
    name:        Optional[str] = None
    description: Optional[str] = None
    status:      Optional[str] = None
    color_tag:   Optional[str] = None

    service_platform: Optional[str] = None
    campaign_goal:    Optional[str] = None
    view_target:      Optional[int] = None
    base_price_per_1k: Optional[float] = None
    currency:         Optional[str] = None

    country_multipliers:    Optional[Dict[str, float]] = None
    duration_multipliers:   Optional[Dict[str, float]] = None
    niche_multipliers:      Optional[Dict[str, float]] = None
    subscriber_multipliers: Optional[Dict[str, float]] = None
    language_multipliers:   Optional[Dict[str, float]] = None

    platform_multiplier:   Optional[float] = None
    delivery_days:         Optional[int]   = None
    delivery_multiplier:   Optional[float] = None
    retention_target_pct:  Optional[int]   = None
    retention_multiplier:  Optional[float] = None

    volume_discounts: Optional[List[Dict[str, Any]]] = None
    min_price:        Optional[float] = None
    max_price:        Optional[float] = None

    ai_prompt_template:     Optional[str] = None
    email_subject_template: Optional[str] = None


class PriceQuoteRequest(BaseModel):
    """
    Used by the frontend Price Calculator to get a server-side quote.
    Matches exactly what the AI generator does at generation time.
    """
    plan_id:    int
    country:    str = "US"
    dur_bucket: str = "mid"       # shorts | short | mid | long | ultra
    niche:      str = "default"
    sub_bucket: str = "mid"       # tiny | small | mid | large | mega
    language:   str = "en"
    view_target: Optional[int] = None   # override plan's view_target if needed


# ─── Routes ───────────────────────────────────────────────────────────────────

@router.get("/kpis")
def get_kpis(db: Session = Depends(get_db)):
    return {
        "total_plans":  db.query(func.count(ScriptPlan.id)).scalar() or 0,
        "active_plans": db.query(func.count(ScriptPlan.id)).filter(ScriptPlan.status == "active").scalar() or 0,
        "draft_plans":  db.query(func.count(ScriptPlan.id)).filter(ScriptPlan.status == "draft").scalar() or 0,
        "total_used":   db.query(func.sum(ScriptPlan.total_used)).scalar() or 0,
    }


@router.get("")
def list_plans(
    status: Optional[str] = Query(None, description="Filter by status: active | draft | archived"),
    db:     Session = Depends(get_db),
):
    q = db.query(ScriptPlan).order_by(ScriptPlan.created_at.desc())
    if status:
        q = q.filter(ScriptPlan.status == status)
    return q.all()


@router.get("/{plan_id}")
def get_plan(plan_id: int, db: Session = Depends(get_db)):
    plan = db.query(ScriptPlan).get(plan_id)
    if not plan:
        raise HTTPException(404, "Plan not found")
    return plan


@router.post("")
def create_plan(payload: PlanBase, db: Session = Depends(get_db)):
    plan = ScriptPlan(**payload.model_dump())
    db.add(plan)
    db.commit()
    db.refresh(plan)
    return plan


@router.patch("/{plan_id}")
def update_plan(plan_id: int, payload: PlanUpdate, db: Session = Depends(get_db)):
    plan = db.query(ScriptPlan).get(plan_id)
    if not plan:
        raise HTTPException(404, "Plan not found")

    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(plan, k, v)

    plan.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(plan)
    return plan


@router.delete("/{plan_id}")
def delete_plan(plan_id: int, db: Session = Depends(get_db)):
    plan = db.query(ScriptPlan).get(plan_id)
    if not plan:
        raise HTTPException(404, "Plan not found")
    db.delete(plan)
    db.commit()
    return {"deleted": True, "id": plan_id}


@router.post("/quote")
def get_price_quote(payload: PriceQuoteRequest, db: Session = Depends(get_db)):
    """
    Server-side price calculator — same formula as ai_generator.calculate_price().
    Used by the frontend Price Calculator modal for accurate quotes.
    """
    plan = db.query(ScriptPlan).get(payload.plan_id)
    if not plan:
        raise HTTPException(404, "Plan not found")

    # Default multiplier maps
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

    view_target = payload.view_target or plan.view_target or 1_000_000
    base_per_1k = plan.base_price_per_1k or 1.0

    country_mults  = plan.country_multipliers    or DEFAULT_COUNTRY
    dur_mults      = plan.duration_multipliers   or DEFAULT_DURATION
    niche_mults    = plan.niche_multipliers      or DEFAULT_NICHE
    sub_mults      = plan.subscriber_multipliers or DEFAULT_SUBS
    lang_mults     = plan.language_multipliers   or DEFAULT_LANG
    vol_discounts  = plan.volume_discounts       or []

    c_mult  = country_mults.get(payload.country,    country_mults.get("default", 1.0))
    d_mult  = dur_mults.get(payload.dur_bucket,     1.0)
    n_mult  = niche_mults.get(payload.niche,        niche_mults.get("default", 1.0))
    s_mult  = sub_mults.get(payload.sub_bucket,     1.0)
    l_mult  = lang_mults.get(payload.language,      lang_mults.get("default", 0.85))
    p_mult  = plan.platform_multiplier  or 1.0
    dv_mult = plan.delivery_multiplier  or 1.0
    r_mult  = plan.retention_multiplier or 1.0

    base_cost = (view_target / 1000) * base_per_1k
    price     = base_cost * c_mult * d_mult * n_mult * p_mult * dv_mult * r_mult * s_mult * l_mult

    # Volume discount
    discount_pct = 0
    for tier in sorted(vol_discounts, key=lambda x: x["threshold"], reverse=True):
        if view_target >= tier["threshold"]:
            discount_pct = tier["discount_pct"]
            break
    price = price * (1 - discount_pct / 100)

    # Guardrails
    if plan.min_price and price < plan.min_price:
        price = plan.min_price
    if plan.max_price and price > plan.max_price:
        price = plan.max_price

    price = round(price, 2)

    return {
        "plan_id":       plan.id,
        "plan_name":     plan.name,
        "view_target":   view_target,
        "currency":      plan.currency,
        "final_price":   price,
        "breakdown": {
            "base_cost":        round(base_cost, 2),
            "country":          f"{payload.country} ×{c_mult}",
            "duration":         f"{payload.dur_bucket} ×{d_mult}",
            "niche":            f"{payload.niche} ×{n_mult}",
            "platform":         f"{plan.service_platform} ×{p_mult}",
            "delivery":         f"{plan.delivery_days}d ×{dv_mult}",
            "retention":        f"{plan.retention_target_pct}% ×{r_mult}",
            "subscribers":      f"{payload.sub_bucket} ×{s_mult}",
            "language":         f"{payload.language} ×{l_mult}",
            "volume_discount":  f"-{discount_pct}%" if discount_pct else "none",
        }
    }