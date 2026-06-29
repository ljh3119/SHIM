from datetime import datetime
from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from src.app import models, utils, auth
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
    
    # 템플릿 호환성을 위한 키 매핑 추가
    stats["total_granted_hours"] = stats["total_allocated_hours"]
    stats["total_used_hours"] = stats["total_approved_hours"]
    stats["exhaustion_rate"] = stats["total_exhaustion_rate"]
    
    now = utils.get_local_now()
    show_setup_banner = now.month in (12, 1)
    next_year = now.year + 1 if now.month == 12 else now.year
    
    if show_setup_banner:
        has_next_year_allocations = db.query(models.UserYearlyLeaveAllocations).filter(
            models.UserYearlyLeaveAllocations.year == next_year
        ).first() is not None
        if has_next_year_allocations:
            show_setup_banner = False
            
    charts_data = admin_service.get_admin_dashboard_charts_data(db, now.year)
    
    settings = db.query(models.SystemSettings).first()
    
    # Uptime 계산 (로컬 임포트로 순환 참조 예방)
    from src.app.main import START_TIME
    uptime_td = now - START_TIME
    days = uptime_td.days
    hours = uptime_td.seconds // 3600
    minutes = (uptime_td.seconds % 3600) // 60
    if days > 0:
        uptime_str = f"{days}일 {hours}시간"
    else:
        if hours > 0:
            uptime_str = f"{hours}시간 {minutes}분"
        else:
            uptime_str = f"{minutes}분"
            
    # 보안 모드 판정
    has_encryption_key = auth.get_encryption_key() is not None
    security_mode_str = "보안 활성(암호화)" if has_encryption_key else "평문 모드(주의)"
    
    # 헬스 체크 임계치 및 지연 상태 판정 (26시간 임계치)
    is_healthy = True
    
    if settings:
        if settings.last_backup_time is not None:
            if (now - settings.last_backup_time).total_seconds() > 26 * 3600:
                is_healthy = False
                
        if settings.last_cleanup_time is not None:
            if (now - settings.last_cleanup_time).total_seconds() > 26 * 3600:
                is_healthy = False
                
        db_size_kb = settings.last_db_size_kb or 0
        if db_size_kb >= 1024:
            db_size_str = f"{db_size_kb / 1024:.1f} MB"
        else:
            db_size_str = f"{db_size_kb} KB"
            
        last_backup_count = settings.last_backup_count or 0
        last_backup_time_str = utils.format_datetime_kst(settings.last_backup_time) if settings.last_backup_time else "백업본 없음 (스케줄링 대기)"
        last_cleanup_time_str = utils.format_datetime_kst(settings.last_cleanup_time) if settings.last_cleanup_time else "정리 이력 없음 (대기 중)"
    else:
        db_size_str = "0 KB"
        last_backup_count = 0
        last_backup_time_str = "백업본 없음 (스케줄링 대기)"
        last_cleanup_time_str = "정리 이력 없음 (대기 중)"
        
    system_metrics = {
        "is_healthy": is_healthy,
        "uptime": uptime_str,
        "security_mode": security_mode_str,
        "db_size": db_size_str,
        "last_backup_time": last_backup_time_str,
        "last_backup_count": last_backup_count,
        "last_cleanup_time": last_cleanup_time_str
    }
    
    return _templates(request).TemplateResponse(request=request, name="admin_dashboard.html", context={
        "admin": admin,
        "active_users_count": stats["active_users_count"],
        "leaves_today_count": stats["leaves_today_count"],
        "pending_leaves_count": stats["pending_leaves_count"],
        "is_approval_required": stats["is_approval_required"],
        "today_used_hours": stats["today_used_hours"],
        "total_allocated_hours": stats["total_allocated_hours"],
        "total_approved_hours": stats["total_approved_hours"],
        "total_exhaustion_rate": stats["total_exhaustion_rate"],
        "recent_leaves": stats["recent_leaves"],
        "today_absentees": stats["today_absentees"],
        "recent_audits": stats["recent_audits"],
        "today_leaves": stats["today_absentees"],  # 템플릿 today_leaves 매핑
        "today_date": now.strftime('%Y-%m-%d'),
        "current_year": now.year,
        "show_setup_banner": show_setup_banner,    # 템플릿 show_setup_banner 매핑
        "next_year": next_year,
        "chart_data": charts_data,
        "stats": stats,
        "system_metrics": system_metrics
    })
