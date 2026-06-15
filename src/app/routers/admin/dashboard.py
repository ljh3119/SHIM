from datetime import datetime
from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from src.app import models, utils
from src.app.database import get_db
from src.app.services import admin_service
from src.app.dependencies import get_current_admin

page_router = APIRouter()
api_router = APIRouter()

def _templates(request: Request):
    return request.app.state.templates

@page_router.get("/dashboard", response_class=HTMLResponse)
def admin_dashboard(
    request: Request,
    db: Session = Depends(get_db),
    admin: models.Users = Depends(get_current_admin)
):
    stats = admin_service.get_admin_dashboard_stats(db)
    
    now = utils.get_local_now()
    show_year_end_notice = now.month in (12, 1)
    next_year = now.year + 1 if now.month == 12 else now.year
    
    if show_year_end_notice:
        has_next_year_allocations = db.query(models.UserYearlyLeaveAllocations).filter(
            models.UserYearlyLeaveAllocations.year == next_year
        ).first() is not None
        if has_next_year_allocations:
            show_year_end_notice = False
            
    charts_data = admin_service.get_admin_dashboard_charts_data(db, now.year)
    
    return _templates(request).TemplateResponse(request=request, name="admin_dashboard.html", context={
        "admin": admin,
        "active_users_count": stats["active_users_count"],
        "leaves_today_count": stats["leaves_today_count"],
        "pending_leaves_count": stats["pending_leaves_count"],
        "is_approval_required": stats["is_approval_required"],
        "today_used_hours": stats["today_used_hours"],
        "recent_leaves": stats["recent_leaves"],
        "current_year": now.year,
        "show_year_end_notice": show_year_end_notice,
        "next_year": next_year,
        "chart_data": charts_data
    })
