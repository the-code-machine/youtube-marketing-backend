from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List

from app.core.database import SessionLocal
from app.services.template_service import TemplateService
from app.schemas.template import TemplateResponse, TemplateCreate, TemplateUpdate

router = APIRouter(prefix="/api/templates", tags=["Email Templates"])

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# --- READ ALL ---
@router.get("/", response_model=List[TemplateResponse])
def list_templates(db: Session = Depends(get_db)):
    service = TemplateService(db)
    return service.get_all_templates()

# --- READ ONE ---
@router.get("/{id}", response_model=TemplateResponse)
def get_template(id: int, db: Session = Depends(get_db)):
    service = TemplateService(db)
    template = service.get_template(id)
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")
    return template

# --- CREATE ---
@router.post("/", response_model=TemplateResponse)
def create_template(payload: TemplateCreate, db: Session = Depends(get_db)):
    service = TemplateService(db)
    return service.create_template(payload)

# --- UPDATE ---
@router.patch("/{id}", response_model=TemplateResponse)
def update_template(id: int, payload: TemplateUpdate, db: Session = Depends(get_db)):
    service = TemplateService(db)
    updated = service.update_template(id, payload)
    if not updated:
        raise HTTPException(status_code=404, detail="Template not found")
    return updated

# --- DELETE ---
@router.delete("/{id}")
def delete_template(id: int, db: Session = Depends(get_db)):
    service = TemplateService(db)
    success = service.delete_template(id)
    if not success:
        raise HTTPException(status_code=404, detail="Template not found")
    return {"message": "Template deleted successfully"}