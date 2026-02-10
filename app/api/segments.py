from fastapi import APIRouter, Depends, Query, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from datetime import datetime, timedelta

from app.core.database import SessionLocal
from app.services.segment_service import SegmentService
from app.schemas.segment import SegmentCard, SegmentKPIs, TableResponse, AIStubResponse

router = APIRouter(prefix="/segments", tags=["Segments & Categorization"])

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# 1. Get All Segment Cards
@router.get("/", response_model=list[SegmentCard])
def get_segments(db: Session = Depends(get_db)):
    service = SegmentService(db)
    return service.get_all_segments()

# 2. Get Segment KPIs
@router.get("/{segment_id}/kpis", response_model=SegmentKPIs)
def get_segment_kpis(
    segment_id: str,
    startDate: str = Query("7d"), # accepts "7d" or ISO date
    endDate: str = Query(None),
    db: Session = Depends(get_db)
):
    service = SegmentService(db)
    
    # Simple date parser
    end = datetime.utcnow()
    if startDate == "7d":
        start = end - timedelta(days=7)
    elif startDate == "30d":
        start = end - timedelta(days=30)
    else:
        # Assume ISO format in prod
        start = end - timedelta(days=7) 

    return service.get_segment_kpis(segment_id, start, end)

# 3. Get Segment Table
@router.get("/{segment_id}/table", response_model=TableResponse)
def get_segment_table(
    segment_id: str,
    page: int = 1,
    limit: int = 20,
    search: str = None,
    db: Session = Depends(get_db)
):
    service = SegmentService(db)
    return service.get_segment_table(segment_id, page, limit, search)

# 4. Export Segment
@router.get("/{segment_id}/export")
def export_segment(
    segment_id: str,
    db: Session = Depends(get_db)
):
    service = SegmentService(db)
    csv_file = service.export_segment_csv(segment_id)
    
    filename = f"segment_{segment_id}_export.csv"
    
    return StreamingResponse(
        iter([csv_file.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )

# 5. AI Summary Stub
@router.post("/ai/segment-summary", response_model=AIStubResponse)
def generate_ai_summary(
    payload: dict, # {segmentId, ...}
    db: Session = Depends(get_db)
):
    # Stub response
    return {
        "summary": "This segment is showing strong growth in the last 7 days. Engagement rates are 15% higher than average.",
        "key_insights": [
            "Dominant region is USA.",
            "Short-form content is driving 80% of new leads."
        ],
        "suggested_actions": [
            "Increase email outreach limit for this segment.",
            "Target 'Gaming' sub-niche."
        ]
    }