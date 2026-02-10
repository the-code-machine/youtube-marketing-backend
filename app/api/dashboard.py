from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from app.core.database import SessionLocal
from app.services.dashboard_service import DashboardService
from app.schemas.dashboard import KpiResponse, MainGraphResponse, MiniGraphResponse
from datetime import datetime

router = APIRouter(prefix="/dashboard", tags=["Dashboard Analytics"])

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@router.get("/kpis", response_model=KpiResponse)
def get_dashboard_kpis(
    viewMode: str = Query("DATA", enum=["DATA", "LEAD", "COMBINED"]),
    dateRange: str = Query("7d", enum=["24h", "7d", "10d", "30d"]),
    db: Session = Depends(get_db)
):
    service = DashboardService(db)
    return service.get_kpis(viewMode, dateRange)

@router.get("/main-graph", response_model=MainGraphResponse)
def get_main_graph(
    viewMode: str = Query("DATA", enum=["DATA", "LEAD", "COMBINED"]),
    dateRange: str = Query("7d"),
    db: Session = Depends(get_db)
):
    service = DashboardService(db)
    return service.get_main_graph(viewMode, dateRange)

@router.get("/kpi-graphs", response_model=MiniGraphResponse)
def get_kpi_graphs(
    viewMode: str = Query("DATA"), 
    db: Session = Depends(get_db)
):
    service = DashboardService(db)
    graphs = service.get_kpi_graphs(viewMode)
    return {"view_mode": viewMode, "graphs": graphs}

@router.get("/status")
def get_system_status():
    return {
        "last_worker_run": datetime.utcnow(),
        "system_health": "operational"
    }

# 5. AI Summary Stub
@router.post("/ai/dashboard-summary")
def get_ai_summary(viewMode: str, dateRange: str):
    return {
        "textSummary": "Channel acquisition is up 12% this week compared to last week.",
        "bulletInsights": [
            "Tech category is performing best.",
            "Email open rates dropped on Tuesday."
        ],
        "recommendations": [
            "Increase daily email limit to 150.",
            "Target 'Gaming' niche next."
        ]
    }