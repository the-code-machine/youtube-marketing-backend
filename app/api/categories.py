from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.core.database import SessionLocal
from app.models.target_category import TargetCategory
from datetime import datetime

router = APIRouter(prefix="/categories", tags=["Categories"])


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.get("/")
def list_categories(db: Session = Depends(get_db)):
    return db.query(TargetCategory).all()


@router.post("/")
def add_category(name: str, youtube_query: str, db: Session = Depends(get_db)):

    cat = TargetCategory(
        name=name,
        youtube_query=youtube_query,
        is_active=True,
        created_at=datetime.utcnow()
    )

    db.add(cat)
    db.commit()
    db.refresh(cat)

    return cat


@router.put("/{cat_id}")
def update_category(cat_id: int, name: str, youtube_query: str, is_active: bool, db: Session = Depends(get_db)):

    cat = db.query(TargetCategory).get(cat_id)
    if not cat:
        raise HTTPException(404)

    cat.name = name
    cat.youtube_query = youtube_query
    cat.is_active = is_active

    db.commit()
    return cat


@router.delete("/{cat_id}")
def delete_category(cat_id: int, db: Session = Depends(get_db)):

    cat = db.query(TargetCategory).get(cat_id)
    if not cat:
        raise HTTPException(404)

    db.delete(cat)
    db.commit()

    return {"status": "deleted"}
