from __future__ import annotations
from datetime import datetime, date, timedelta
from sqlalchemy.orm import Session, contains_eager, joinedload
from sqlalchemy import extract
from .. import models

def get_admin_dashboard_stats(db: Session):
    today = datetime.now()
    day_start = datetime.combine(today.date(), datetime.min.time())
    next_day_start = day_start + timedelta(days=1)
    
    # KPIs
    users = db.query(models.Users).filter(models.Users.role != "ADMIN").all()
    active_users_count = len([u for u in users if u.is_active])
    
    # 오늘 신청 건수(created_at 기준)
    leaves_today_count = db.query(models.Leaves).filter(
        models.Leaves.created_at >= day_start,
        models.Leaves.created_at < next_day_start
    ).count()
    
    pending_leaves_count = db.query(models.Leaves).filter(models.Leaves.status == "PENDING").count()
    
    from .leave_policy import get_system_settings
    setting = get_system_settings(db)
    is_approval_required = bool(setting.is_approval_required) if setting else False

    # 금일 총 사용 연차(date 기준, 차감 대상인 것만)
    leaves_used_today = db.query(models.Leaves).filter(models.Leaves.date == today.date(), models.Leaves.is_deductive == True).all()
    today_used_hours = sum(float(l.snapshot_deduction_hours or 0) for l in leaves_used_today if l.status not in ("CANCELED", "REJECTED"))
    
    # Last 7 days timeline (N+1 최적화를 위해 joinedload(models.Leaves.user) 추가)
    seven_days_ago = today - timedelta(days=7)
    recent_leaves = db.query(models.Leaves).options(joinedload(models.Leaves.user)).filter(
        models.Leaves.created_at >= seven_days_ago
    ).order_by(models.Leaves.created_at.desc()).all()
    
    return {
        "active_users_count": active_users_count,
        "leaves_today_count": leaves_today_count,
        "pending_leaves_count": pending_leaves_count,
        "is_approval_required": is_approval_required,
        "today_used_hours": today_used_hours,
        "recent_leaves": recent_leaves,
    }

def get_leaves_timeline_query(
    db: Session,
    year: int,
    month: int = 0,
    user_id: str = "",
    company: str = "",
    team: str = "",
    leave_status: str = "",
):
    query = (
        db.query(models.Leaves)
        .join(models.Users, models.Leaves.user_id == models.Users.user_id)
        .options(contains_eager(models.Leaves.user))
        .filter(models.Leaves.year == year)
    )
    if month > 0:
        query = query.filter(extract("month", models.Leaves.date) == month)
    if user_id:
        query = query.filter(models.Leaves.user_id == user_id)
    if company:
        query = query.filter(models.Users.company == company)
    if team:
        query = query.filter(models.Users.team == team)
    if leave_status:
        query = query.filter(models.Leaves.status == leave_status)
    return query

def get_yearly_allocation_map(db: Session, user_ids: list[str], year: int) -> dict[str, int]:
    if not user_ids:
        return {}
    try:
        rows = db.query(models.UserYearlyLeaveAllocations).filter(
            models.UserYearlyLeaveAllocations.user_id.in_(user_ids),
            models.UserYearlyLeaveAllocations.year == year
        ).all()
        return {row.user_id: int(row.allocated_hours) for row in rows}
    except Exception:
        db.rollback()
        return {}

def get_audit_logs_query(
    db: Session,
    actor_id: str = "",
    action: str = "",
    start_date: date | None = None,
    end_date: date | None = None,
):
    # N+1 최적화를 위해 joinedload(models.AuditLogs.actor) 추가
    # actor_id가 NULL인 감사 로그(하드 삭제된 사원)도 조회할 수 있도록 outerjoin 형태로 동작하는 joinedload가 적합합니다.
    query = db.query(models.AuditLogs).options(joinedload(models.AuditLogs.actor))
    if actor_id:
        query = query.filter(models.AuditLogs.actor_id == actor_id)
    if action:
        query = query.filter(models.AuditLogs.action.contains(action))
    if start_date:
        query = query.filter(models.AuditLogs.timestamp >= datetime.combine(start_date, datetime.min.time()))
    if end_date:
        query = query.filter(models.AuditLogs.timestamp < datetime.combine(end_date + timedelta(days=1), datetime.min.time()))
    return query
