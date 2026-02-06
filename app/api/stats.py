from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.core.database import SessionLocal
from app.models import DailyStats, CountryStats, CategoryStats

router = APIRouter(prefix="/stats", tags=["Stats"])


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.get("/daily")
def daily(db: Session = Depends(get_db)):
    return db.query(DailyStats).order_by(DailyStats.stat_date.desc()).all()


@router.get("/country")
def country(db: Session = Depends(get_db)):
    return db.query(CountryStats).order_by(CountryStats.stat_date.desc()).all()


@router.get("/category")
def category(db: Session = Depends(get_db)):
    return db.query(CategoryStats).order_by(CategoryStats.stat_date.desc()).all()
