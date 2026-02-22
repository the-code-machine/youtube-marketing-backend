from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import List, Optional
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


# ── Pydantic schemas (inline, no separate file needed) ───────────────────────

class PlanBase(BaseModel):
    name: str
    description: Optional[str] = None
    status: str = "active"
    color_tag: str = "blue"
    service_type: str
    pitch_angle: Optional[str] = None
    pricing_model: str = "flat_rate"
    base_price: Optional[float] = None
    price_per_view: Optional[float] = None
    price_per_1k: Optional[float] = None
    revenue_share_pct: Optional[float] = None
    currency: str = "USD"
    min_guarantee: Optional[float] = None
    min_views: Optional[int] = None
    max_views: Optional[int] = None
    min_subscribers: Optional[int] = None
    max_subscribers: Optional[int] = None
    min_duration_sec: Optional[int] = None
    max_duration_sec: Optional[int] = None
    target_countries: Optional[List[str]] = None
    ai_prompt_template: str
    email_subject_template: Optional[str] = None


class PlanUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None
    color_tag: Optional[str] = None
    service_type: Optional[str] = None
    pitch_angle: Optional[str] = None
    pricing_model: Optional[str] = None
    base_price: Optional[float] = None
    price_per_view: Optional[float] = None
    price_per_1k: Optional[float] = None
    revenue_share_pct: Optional[float] = None
    currency: Optional[str] = None
    min_guarantee: Optional[float] = None
    min_views: Optional[int] = None
    max_views: Optional[int] = None
    min_subscribers: Optional[int] = None
    max_subscribers: Optional[int] = None
    min_duration_sec: Optional[int] = None
    max_duration_sec: Optional[int] = None
    target_countries: Optional[List[str]] = None
    ai_prompt_template: Optional[str] = None
    email_subject_template: Optional[str] = None


# ── Routes ────────────────────────────────────────────────────────────────────

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
    status: Optional[str] = Query(None),
    db: Session = Depends(get_db)
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
    return {"deleted": True}