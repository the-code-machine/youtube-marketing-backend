from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from app.core.database import SessionLocal
from app.services.dashboard_service import DashboardService
from app.schemas.dashboard import KpiResponse, MainGraphResponse, SystemStatusResponse
from datetime import datetime

router = APIRouter(prefix="/dashboard", tags=["Dashboard Analytics"])

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# 1. KPI Summary
@router.get("/kpis", response_model=KpiResponse)
def get_dashboard_kpis(
    viewMode: str = Query("DATA", enum=["DATA", "LEAD", "COMBINED"]),
    dateRange: str = Query("7d", enum=["24h", "7d", "30d"]),
    db: Session = Depends(get_db)
):
    service = DashboardService(db)
    return service.get_kpis(viewMode, dateRange)

# 2. Main Graph
@router.get("/main-graph", response_model=MainGraphResponse)
def get_main_graph(
    viewMode: str = Query("DATA", enum=["DATA", "LEAD", "COMBINED"]),
    dateRange: str = Query("7d"),
    db: Session = Depends(get_db)
):
    service = DashboardService(db)
    return service.get_main_graph(viewMode, dateRange)

# 3. Mini KPI Graphs (Stubbed for performance, usually calls similar logic to main graph)
@router.get("/kpi-graphs")
def get_kpi_graphs(
    viewMode: str = Query("DATA", enum=["DATA", "LEAD", "COMBINED"]), 
    db: Session = Depends(get_db)
):
    """
    Returns the small sparkline data for each KPI card.
    """
    service = DashboardService(db)
    graphs = service.get_kpi_graphs(viewMode)
    
    return {
        "viewMode": viewMode,
        "graphs": graphs
    }

# 4. System Status
@router.get("/status", response_model=SystemStatusResponse)
def get_system_status():
    # In production, fetch this from a Redis key or SystemLog table
    return {
        "last_worker_run": datetime.utcnow(),
        "last_lead_update": datetime.utcnow(),
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