from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from app.core.database import SessionLocal
from app.services.ai_store_service import AIStoreService
from app.schemas.ai_store import AIStoreResponse, AIStoreKPIs

router = APIRouter(prefix="/api/ai-store", tags=["AI Store"])

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@router.get("/", response_model=AIStoreResponse)
def get_ai_store_items(
    page: int = 1, 
    limit: int = 20, 
    search: str = None, 
    status: str = None,
    db: Session = Depends(get_db)
):
    """
    Get a paginated history of all AI generated content across campaigns.
    Rich data includes channel thumbnails and stats.
    """
    service = AIStoreService(db)
    return service.get_ai_history(page, limit, search, status)

@router.get("/kpis", response_model=AIStoreKPIs)
def get_ai_store_kpis(db: Session = Depends(get_db)):
    """
    Get usage statistics for the AI Store (Total Generated, Words Used, etc).
    """
    service = AIStoreService(db)
    return service.get_kpis()