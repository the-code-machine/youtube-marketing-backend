from fastapi import APIRouter, Depends, Query, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from datetime import datetime, timedelta

from app.core.database import SessionLocal
from app.services.segment_service import SegmentService
from app.schemas.segment import SegmentCard, SegmentKPIs, TableResponse, GraphResponse, GraphSeries

router = APIRouter(prefix="/segments", tags=["Segments & Categorization"])

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@router.get("/", response_model=list[SegmentCard])
def get_segments(db: Session = Depends(get_db)):
    service = SegmentService(db)
    return service.get_all_segments()

@router.get("/{segment_id}/kpis", response_model=SegmentKPIs)
def get_segment_kpis(
    segment_id: str,
    startDate: str = Query("7d"),
    db: Session = Depends(get_db)
):
    service = SegmentService(db)
    # Simple Date Logic
    end = datetime.utcnow()
    days = int(startDate.replace("d", "")) if "d" in startDate else 7
    start = end - timedelta(days=days)

    return service.get_segment_kpis(segment_id, start, end)

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


@router.get("/{segment_id}/export")
def export_segment(segment_id: str, db: Session = Depends(get_db)):
    service = SegmentService(db)
    csv_file = service.export_segment_csv(segment_id)
    filename = f"segment_{segment_id}_export.csv"
    return StreamingResponse(
        iter([csv_file.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )
    
# ... (imports remain similar)

@router.get("/{segment_id}/graphs", response_model=GraphResponse)
def get_segment_graphs(
    segment_id: str,
    startDate: str = Query("30d"),
    granularity: str = "daily",
    db: Session = Depends(get_db)
):
    service = SegmentService(db)
    
    end = datetime.utcnow()
    days = int(startDate.replace("d", "")) if "d" in startDate else 30
    start = end - timedelta(days=days)

    return service.get_segment_graphs(segment_id, start, end, granularity)