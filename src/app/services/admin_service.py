from datetime import datetime, date, timedelta, timezone
from sqlalchemy.orm import Session, contains_eager, joinedload
from sqlalchemy import extract
from .. import models, utils

def get_admin_dashboard_stats(db: Session):
    today = utils.get_local_now()
    day_start_local = datetime.combine(today.date(), datetime.min.time()).replace(tzinfo=today.tzinfo)
    day_start = day_start_local.astimezone(timezone.utc).replace(tzinfo=None)
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

    # 오늘 부재자 목록 (APPROVED/PENDING) - N+1 방지
    today_leaves = db.query(models.Leaves).options(joinedload(models.Leaves.user)).filter(
        models.Leaves.date == today.date(),
        models.Leaves.status.in_(["APPROVED", "PENDING"])
    ).all()

    # 최근 감사 로그 10건 - N+1 방지
    recent_audits = db.query(models.AuditLogs).options(
        joinedload(models.AuditLogs.actor)
    ).order_by(models.AuditLogs.id.desc()).limit(10).all()
    
    return {
        "active_users_count": active_users_count,
        "leaves_today_count": leaves_today_count,
        "pending_leaves_count": pending_leaves_count,
        "is_approval_required": is_approval_required,
        "today_used_hours": today_used_hours,
        "recent_leaves": recent_leaves,
        "today_absentees": today_leaves,
        "recent_audits": recent_audits,
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
        import calendar as cal_module
        num_days = cal_module.monthrange(year, month)[1]
        query = query.filter(
            models.Leaves.date >= date(year, month, 1),
            models.Leaves.date <= date(year, month, num_days)
        )
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
    except Exception as e:
        db.rollback()
        import logging
        logging.getLogger("shim.admin").warning(
            f"Failed to get yearly allocation map: {e}", exc_info=True
        )
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

def get_admin_dashboard_charts_data(db: Session, year: int):
    # 1. 팀별 사용 및 잔여 연차 데이터 수집
    active_users = db.query(models.Users).filter(
        models.Users.role != "ADMIN",
        models.Users.is_active == True
    ).all()
    
    user_ids = [u.user_id for u in active_users]
    
    # 각 사용자의 해당 연도 할당량
    alloc_map = get_yearly_allocation_map(db, user_ids, year)
    
    # 각 사용자의 사용 연차 합계 (APPROVED 상태이며 차감 대상인 것)
    leaves_approved = db.query(models.Leaves).filter(
        models.Leaves.user_id.in_(user_ids) if user_ids else False,
        models.Leaves.year == year,
        models.Leaves.status == "APPROVED",
        models.Leaves.is_deductive == True
    ).all()
    
    user_used_map = {uid: 0.0 for uid in user_ids}
    for leave in leaves_approved:
        user_used_map[leave.user_id] += float(leave.snapshot_deduction_hours or 0)
        
    team_data = {}
    for user in active_users:
        team_name = user.team or "미지정"
        if team_name not in team_data:
            team_data[team_name] = {"used": 0.0, "remaining": 0.0}
            
        alloc_hours = float(alloc_map.get(user.user_id, 0))
        used_hours = user_used_map.get(user.user_id, 0.0)
        remaining_hours = max(0.0, alloc_hours - used_hours)
        
        team_data[team_name]["used"] += used_hours
        team_data[team_name]["remaining"] += remaining_hours
        
    sorted_teams = sorted(team_data.keys())
    used_hours_list = [team_data[t]["used"] for t in sorted_teams]
    remaining_hours_list = [team_data[t]["remaining"] for t in sorted_teams]
    
    # 2. 월별 사용 트렌드 (1~12월 각각의 사용 시간 합산)
    # 해당 연도 전체 APPROVED 차감 대상 연차 가져오기 (전체 유저 대상)
    all_leaves_year = db.query(models.Leaves).filter(
        models.Leaves.year == year,
        models.Leaves.status == "APPROVED",
        models.Leaves.is_deductive == True
    ).all()
    
    monthly_hours = [0.0] * 12
    for leave in all_leaves_year:
        # leave.date는 datetime.date 타입
        if leave.date:
            month_idx = leave.date.month - 1  # 0 to 11
            if 0 <= month_idx < 12:
                monthly_hours[month_idx] += float(leave.snapshot_deduction_hours or 0)
                
    return {
        "teams": sorted_teams,
        "used_hours": used_hours_list,
        "remaining_hours": remaining_hours_list,
        "monthly_hours": monthly_hours
    }

