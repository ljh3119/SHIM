from fastapi import APIRouter, Depends, Request, Form, status, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError
from datetime import datetime, date as date_cls
import calendar as cal_module

from .. import models, database, auth
from ..database import get_db
from ..services.leave_policy import (
    LeaveInputValidationError,
    LeaveStatusTransitionError,
    apply_leave_status_transition,
    build_snapshot_from_timerange,
    get_default_leave_status,
    resolve_time_policy_setting,
)

router = APIRouter(prefix="/user", tags=["user"])


def _templates(request: Request):
    return request.app.state.templates

def build_year_options(now_year: int, data_years=None, past_span: int = 5, future_span: int = 10):
    years = [y for y in (data_years or []) if y is not None]
    min_data_year = min(years) if years else now_year
    max_data_year = max(years) if years else now_year
    start = min(now_year - past_span, min_data_year)
    end = max(now_year + future_span, max_data_year)
    return list(range(start, end + 1))


def _minute_options(start_minute: int, end_minute: int, step_minute: int) -> list[str]:
    options: list[str] = []
    cursor = start_minute
    while cursor <= end_minute:
        hh = cursor // 60
        mm = cursor % 60
        options.append(f"{hh:02d}:{mm:02d}")
        cursor += step_minute
    if options:
        end_label = f"{end_minute // 60:02d}:{end_minute % 60:02d}"
        if options[-1] != end_label:
            options.append(end_label)
    return options


def resolve_user_yearly_allocated_hours(db: Session, user: models.Users, year: int) -> int:
    try:
        allocation = db.query(models.UserYearlyLeaveAllocations).filter(
            models.UserYearlyLeaveAllocations.user_id == user.user_id,
            models.UserYearlyLeaveAllocations.year == year
        ).first()
        if allocation:
            return int(allocation.allocated_hours)
    except SQLAlchemyError:
        # 네트워크 스토리지 일시 장애 시에도 대시보드를 fallback 값으로 유지
        db.rollback()
    return int(user.total_leave_hours or 0)

def get_current_user(request: Request, db: Session = Depends(get_db)):
    user_id = auth.get_current_user_from_token(request)
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    user = db.query(models.Users).filter(models.Users.user_id == user_id).first()
    if not user or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not active")
    return user

@router.get("/dashboard", response_class=HTMLResponse)
async def user_dashboard(request: Request, year: int = None, month: int = None, db: Session = Depends(get_db)):
    try:
        user = get_current_user(request, db)
    except HTTPException:
        return RedirectResponse(url="/", status_code=status.HTTP_302_FOUND)
    
    if user.is_admin and (getattr(user, 'role', None) or 'ADMIN') == 'ADMIN':
        return RedirectResponse(url="/admin/dashboard", status_code=status.HTTP_302_FOUND)
    
    now = datetime.now()
    current_year = year if year else now.year
    leave_year_rows = db.query(models.Leaves.year).filter(models.Leaves.user_id == user.user_id).distinct().all()
    leave_years = [row[0] for row in leave_year_rows]
    year_options = build_year_options(now.year, leave_years)
    
    # 연간 통계
    yearly_leaves = db.query(models.Leaves).filter(
        models.Leaves.user_id == user.user_id,
        models.Leaves.year == current_year
    ).order_by(models.Leaves.date.desc()).all()
    
    time_granularity_minutes, lunch_start_minute, lunch_end_minute, work_start_minute, work_end_minute = resolve_time_policy_setting(db)
    time_options = _minute_options(work_start_minute, work_end_minute, time_granularity_minutes)
    
    total_allocated_hours = resolve_user_yearly_allocated_hours(db, user, current_year)
    used_hours = sum(float(leave.snapshot_deduction_hours or 0) for leave in yearly_leaves if leave.status not in ("CANCELED", "REJECTED"))
    remaining_hours = total_allocated_hours - used_hours
    
    # 연간(12개월) 캘린더 데이터
    yearly_day_leaves_map = {m: {} for m in range(1, 13)}
    for l in yearly_leaves:
        month_key = l.date.month
        day_key = l.date.day
        if day_key not in yearly_day_leaves_map[month_key]:
            yearly_day_leaves_map[month_key][day_key] = []
        yearly_day_leaves_map[month_key][day_key].append(l)

    month_calendar_meta = {}
    for m in range(1, 13):
        first_weekday_monday0, num_days = cal_module.monthrange(current_year, m)
        # Jinja 템플릿에서는 일요일 시작(일~토) 기준으로 그리기 위해 변환
        first_weekday_sunday0 = (first_weekday_monday0 + 1) % 7
        month_calendar_meta[m] = {"num_days": num_days, "offset": first_weekday_sunday0}

    # 선택 연도의 공휴일 맵
    year_start = date_cls(current_year, 1, 1)
    year_end = date_cls(current_year, 12, 31)
    holidays = db.query(models.Holidays).filter(
        models.Holidays.date >= year_start,
        models.Holidays.date <= year_end
    ).all()
    holiday_map = {(h.date.month, h.date.day): h.name for h in holidays}
    
    ctx = {
        "user": user,
        "leaves": yearly_leaves,
        "total_allocated_hours": total_allocated_hours,
        "used_hours": used_hours,
        "remaining_hours": remaining_hours,
        "yearly_day_leaves_map": yearly_day_leaves_map,
        "month_calendar_meta": month_calendar_meta,
        "holiday_map": holiday_map,
        "selected_year": current_year,
        "current_year": now.year,
        "year_options": year_options,
        "time_granularity_minutes": time_granularity_minutes,
        "lunch_start_minute": lunch_start_minute,
        "lunch_end_minute": lunch_end_minute,
        "work_start_minute": work_start_minute,
        "work_end_minute": work_end_minute,
        "time_options": time_options,
    }

    # --- 역할 기반 추가 데이터 ---
    user_role = getattr(user, 'role', None) or 'STAFF'
    ctx["user_role"] = user_role

    # 팀 캘린더: 같은 팀원의 당월 휴가 현황 (STAFF, TEAM_LEAD 공용)
    setting = db.query(models.SystemSettings).first()
    team_calendar_visible = bool(getattr(setting, 'team_calendar_visible', True)) if setting else True
    is_approval_required = bool(setting.is_approval_required) if setting else False
    ctx["team_calendar_visible"] = team_calendar_visible
    ctx["is_approval_required"] = is_approval_required

    # 팀장: 결재 대기 건 목록 (결재 ON + TEAM_LEAD)
    pending_team_leaves = []
    if user_role == 'TEAM_LEAD' and is_approval_required and user.team:
        pending_team_leaves = (
            db.query(models.Leaves)
            .join(models.Users, models.Leaves.user_id == models.Users.user_id)
            .filter(
                models.Users.team == user.team,
                models.Users.company == user.company,
                models.Leaves.status == "PENDING",
                models.Leaves.user_id != user.user_id,  # 셀프 결재 제외
            )
            .order_by(models.Leaves.created_at.desc())
            .all()
        )
    ctx["pending_team_leaves"] = pending_team_leaves

    return _templates(request).TemplateResponse(request=request, name="user_dashboard.html", context=ctx)

@router.get("/team-calendar", response_class=HTMLResponse)
async def user_team_calendar(request: Request, year: int = None, month: int = None, db: Session = Depends(get_db)):
    try:
        user = get_current_user(request, db)
    except HTTPException:
        return RedirectResponse(url="/", status_code=status.HTTP_302_FOUND)

    setting = db.query(models.SystemSettings).first()
    team_calendar_visible = bool(getattr(setting, 'team_calendar_visible', True)) if setting else True
    if not team_calendar_visible:
        return RedirectResponse(url="/user/dashboard", status_code=status.HTTP_302_FOUND)

    now = datetime.now()
    display_year = year if year else now.year
    display_month = month if month else now.month
    
    num_days = cal_module.monthrange(display_year, display_month)[1]
    month_start = date_cls(display_year, display_month, 1)
    month_end = date_cls(display_year, display_month, num_days)

    user_role = getattr(user, 'role', 'STAFF')

    team_members = []
    team_leaves_map = {}
    
    # PM은 전사 데이터 조회 (관리자와 동일), 그 외에는 소속 팀 기준 조회
    if user_role == 'PM':
        team_members = db.query(models.Users).filter(
            models.Users.is_active == True,
            models.Users.user_id != user.user_id,
            models.Users.is_admin == False,
        ).order_by(models.Users.user_name.asc()).all()
    elif user.team:
        team_members = db.query(models.Users).filter(
            models.Users.team == user.team,
            models.Users.is_active == True,
            models.Users.user_id != user.user_id,
            models.Users.is_admin == False,
        ).order_by(models.Users.user_name.asc()).all()

    if team_members:
        team_member_ids = [m.user_id for m in team_members]
        team_leaves_raw = db.query(models.Leaves).filter(
            models.Leaves.user_id.in_(team_member_ids),
            models.Leaves.date >= month_start,
            models.Leaves.date <= month_end,
            models.Leaves.status.in_(["APPROVED", "PENDING"]),
        ).all()

        team_leaves_map = {m.user_id: {} for m in team_members}
        for lv in team_leaves_raw:
            if lv.user_id in team_leaves_map:
                d = lv.date.day
                if d not in team_leaves_map[lv.user_id]:
                    team_leaves_map[lv.user_id][d] = []
                team_leaves_map[lv.user_id][d].append(lv)

    weekday_labels = ["월", "화", "수", "목", "금", "토", "일"]
    team_cal_day_weekday = {
        d: weekday_labels[cal_module.weekday(display_year, display_month, d)] for d in range(1, num_days + 1)
    }
    team_cal_weekend_days = [
        d for d in range(1, num_days + 1) if cal_module.weekday(display_year, display_month, d) >= 5
    ]
    team_holidays = db.query(models.Holidays).filter(
        models.Holidays.date >= month_start,
        models.Holidays.date <= month_end
    ).all()
    team_cal_holiday_map = {h.date.day: h.name for h in team_holidays}
    
    is_approval_required = bool(setting.is_approval_required) if setting else False

    ctx = {
        "user": user,
        "user_role": user_role,
        "is_approval_required": is_approval_required,
        "team_calendar_visible": team_calendar_visible,
        "team_members": team_members,
        "team_leaves_map": team_leaves_map,
        "team_name": user.team if user_role != 'PM' else "전사",
        "team_cal_year": display_year,
        "team_cal_month": display_month,
        "team_cal_num_days": num_days,
        "team_cal_day_weekday": team_cal_day_weekday,
        "team_cal_weekend_days": team_cal_weekend_days,
        "team_cal_holiday_map": team_cal_holiday_map,
        "current_year": now.year,
        "current_month": now.month,
    }
    return _templates(request).TemplateResponse(request=request, name="user_team_calendar.html", context=ctx)

@router.get("/history", response_class=HTMLResponse)
async def user_history(request: Request, year: int = None, db: Session = Depends(get_db)):
    try:
        user = get_current_user(request, db)
    except HTTPException:
        return RedirectResponse(url="/", status_code=status.HTTP_302_FOUND)

    now = datetime.now()
    current_year = year if year else now.year
    leave_year_rows = db.query(models.Leaves.year).filter(models.Leaves.user_id == user.user_id).distinct().all()
    leave_years = [row[0] for row in leave_year_rows]
    year_options = build_year_options(now.year, leave_years)

    # 연간 통계
    yearly_leaves = db.query(models.Leaves).filter(
        models.Leaves.user_id == user.user_id,
        models.Leaves.year == current_year
    ).order_by(models.Leaves.date.desc()).all()

    total_allocated_hours = resolve_user_yearly_allocated_hours(db, user, current_year)
    used_hours = sum(float(leave.snapshot_deduction_hours or 0) for leave in yearly_leaves if leave.status not in ("CANCELED", "REJECTED"))
    remaining_hours = total_allocated_hours - used_hours

    setting = db.query(models.SystemSettings).first()
    team_calendar_visible = bool(getattr(setting, 'team_calendar_visible', True)) if setting else True
    is_approval_required = bool(setting.is_approval_required) if setting else False
    user_role = getattr(user, 'role', 'STAFF')

    ctx = {
        "user": user,
        "user_role": user_role,
        "leaves": yearly_leaves,
        "total_allocated_hours": total_allocated_hours,
        "used_hours": used_hours,
        "remaining_hours": remaining_hours,
        "selected_year": current_year,
        "current_year": now.year,
        "year_options": year_options,
        "team_calendar_visible": team_calendar_visible,
        "is_approval_required": is_approval_required,
    }
    return _templates(request).TemplateResponse(request=request, name="user_history.html", context=ctx)
@router.post("/leave")
async def apply_leave(
    request: Request,
    date_str: str = Form(...),
    start_time: str | None = Form(None),
    end_time: str | None = Form(None),
    db: Session = Depends(get_db)
):
    try:
        user = get_current_user(request, db)
    except HTTPException:
        return JSONResponse(status_code=401, content={"detail": "Not authenticated"})
    
    leave_date = datetime.strptime(date_str, "%Y-%m-%d").date()
    if leave_date.weekday() >= 5:
        return JSONResponse(
            status_code=400,
            content={"message": f"{leave_date}은(는) 주말이라 연차를 신청할 수 없습니다."}
        )

    holiday = db.query(models.Holidays).filter(models.Holidays.date == leave_date).first()
    if holiday:
        return JSONResponse(
            status_code=400,
            content={"message": f"{leave_date}은(는) 공휴일({holiday.name})이라 연차를 신청할 수 없습니다."}
        )

    if not start_time or not end_time:
        return JSONResponse(status_code=400, content={"message": "시작/종료 시간을 입력해 주세요."})
    granularity, lunch_start, lunch_end, work_start, work_end = resolve_time_policy_setting(db)
    try:
        resolved_snapshots = [
            build_snapshot_from_timerange(
                start_time=start_time,
                end_time=end_time,
                granularity_minutes=granularity,
                lunch_start_minute=lunch_start,
                lunch_end_minute=lunch_end,
                work_start_minute=work_start,
                work_end_minute=work_end,
            )
        ]
    except LeaveInputValidationError as exc:
        return JSONResponse(status_code=400, content={"message": str(exc)})

    # 8시간 초과 검증
    daily_leaves = db.query(models.Leaves).filter(
        models.Leaves.user_id == user.user_id,
        models.Leaves.date == leave_date
    ).all()

    for selected in resolved_snapshots:
        for existing in daily_leaves:
            if existing.status in ("CANCELED", "REJECTED"):
                continue
            if existing.snapshot_start_min is None or existing.snapshot_end_min is None:
                continue
            if selected.start_min < existing.snapshot_end_min and selected.end_min > existing.snapshot_start_min:
                return JSONResponse(
                    status_code=400,
                    content={"message": "기존 신청 내역과 시간이 겹치는 시간대는 신청할 수 없습니다."}
                )

    current_day_hours = sum(float(l.snapshot_deduction_hours or 0) for l in daily_leaves if l.status not in ("CANCELED", "REJECTED"))
    requested_hours = sum(float(s.deduction_hours or 0) for s in resolved_snapshots)
    if current_day_hours + requested_hours > 8:
        return JSONResponse(status_code=400, content={"message": "하루 최대 8시간을 초과하여 연차를 신청할 수 없습니다."})

    # PM은 결재를 타지 않고 바로 승인 (사용자 요청 사항)
    if getattr(user, "role", "STAFF") == "PM":
        leave_status = "APPROVED"
    else:
        leave_status = get_default_leave_status(db)

    for snapshot in resolved_snapshots:
        db.add(models.Leaves(
            user_id=user.user_id,
            date=leave_date,
            snapshot_slot_label=snapshot.slot_label,
            snapshot_start_min=snapshot.start_min,
            snapshot_end_min=snapshot.end_min,
            snapshot_deduction_hours=snapshot.deduction_hours,
            status=leave_status,
            year=leave_date.year
        ))
    db.commit()
    
    return JSONResponse(status_code=200, content={"message": f"연차 {len(resolved_snapshots)}건이 성공적으로 신청되었습니다."})

@router.post("/change-password")
async def change_password(
    request: Request,
    current_password: str = Form(...),
    new_password: str = Form(...),
    db: Session = Depends(get_db)
):
    try:
        user = get_current_user(request, db)
    except HTTPException:
        return JSONResponse(status_code=401, content={"detail": "Not authenticated"})
        
    if not auth.verify_password(current_password, user.password):
        return JSONResponse(status_code=400, content={"message": "현재 비밀번호가 일치하지 않습니다."})
        
    user.password = auth.get_password_hash(new_password)
    
    audit = models.AuditLogs(
        actor_id=user.user_id,
        action="CHANGE_PASSWORD",
        target_info=f"User:{user.user_id}",
        old_data="*****",
        new_data="*****"
    )
    db.add(audit)
    db.commit()
    
    return JSONResponse(status_code=200, content={"message": "비밀번호가 성공적으로 변경되었습니다. 다음 로그인부터 새 비밀번호를 사용하세요."})


# ── 결재 관리 엔드포인트 (팀장/PM) ────────────────────────────────────────────

def _get_approver(request: Request, db: Session) -> models.Users:
    """TEAM_LEAD 또는 PM 역할 검증. 결재 기능이 OFF이면 403."""
    user = get_current_user(request, db)
    user_role = getattr(user, "role", None) or "STAFF"
    if user_role not in ["TEAM_LEAD", "PM"]:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="결재 권한이 필요합니다.")
    setting = db.query(models.SystemSettings).first()
    if not setting or not setting.is_approval_required:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="결재 기능이 비활성화 상태입니다.")
    return user


def _validate_approvable_leave(approver: models.Users, leave: models.Leaves, db: Session) -> models.Users:
    """결재 대상 휴가 검증: 같은 팀·셀프 결재 금지."""
    if leave.user_id == approver.user_id:
        raise HTTPException(status_code=400, detail="본인 신청에 대해서는 결재할 수 없습니다.")
    target_user = db.query(models.Users).filter(models.Users.user_id == leave.user_id).first()
    if not target_user:
        raise HTTPException(status_code=404, detail="신청자 정보를 찾을 수 없습니다.")
    
    # PM은 전사 결재 가능? 아니면 팀장과 동일하게 팀내? 
    # 보통 PM은 프로젝트 단위지만 여기서는 직급 체계이므로 팀장과 동일하게 팀내 결재로 일단 유지 (필요시 전사로 확장)
    if target_user.team != approver.team or target_user.company != approver.company:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="다른 팀의 신청에 대해서는 결재할 수 없습니다.")
    return target_user


@router.get("/approvals", response_class=HTMLResponse)
async def user_approvals(request: Request, db: Session = Depends(get_db)):
    try:
        approver = _get_approver(request, db)
    except HTTPException:
        return RedirectResponse(url="/user/dashboard", status_code=status.HTTP_302_FOUND)

    user_role = getattr(approver, "role", "STAFF")
    setting = db.query(models.SystemSettings).first()
    team_calendar_visible = bool(getattr(setting, 'team_calendar_visible', True)) if setting else True
    is_approval_required = bool(setting.is_approval_required) if setting else False

    pending_leaves = (
        db.query(models.Leaves)
        .join(models.Users, models.Leaves.user_id == models.Users.user_id)
        .filter(
            models.Users.team == approver.team,
            models.Users.company == approver.company,
            models.Leaves.status == "PENDING",
            models.Leaves.user_id != approver.user_id,
        )
        .order_by(models.Leaves.created_at.desc())
        .all()
    )

    ctx = {
        "user": approver,
        "user_role": user_role,
        "team_calendar_visible": team_calendar_visible,
        "is_approval_required": is_approval_required,
        "pending_leaves": pending_leaves,
    }
    return _templates(request).TemplateResponse(request=request, name="user_approvals.html", context=ctx)


@router.post("/team-approve/{leave_id}")
async def team_approve_leave(
    request: Request,
    leave_id: int,
    db: Session = Depends(get_db),
):
    try:
        approver = _get_approver(request, db)
    except HTTPException as exc:
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})

    leave = db.query(models.Leaves).filter(models.Leaves.id == leave_id).first()
    if not leave:
        return JSONResponse(status_code=404, content={"message": "신청 건을 찾을 수 없습니다."})

    try:
        _validate_approvable_leave(approver, leave, db)
    except HTTPException as exc:
        return JSONResponse(status_code=exc.status_code, content={"message": exc.detail})

    try:
        transition = apply_leave_status_transition(leave=leave, status_value="APPROVED")
    except LeaveStatusTransitionError as exc:
        return JSONResponse(status_code=400, content={"message": str(exc)})

    db.add(
        models.AuditLogs(
            actor_id=approver.user_id,
            action="APPROVE_LEAVE",
            target_info=f"Leave:{leave_id}",
            old_data=transition.audit_old_data,
            new_data=transition.audit_new_data,
        )
    )
    db.commit()
    return JSONResponse(status_code=200, content={"message": "승인되었습니다."})


@router.post("/team-reject/{leave_id}")
async def team_reject_leave(
    request: Request,
    leave_id: int,
    rejection_reason: str = Form(""),
    db: Session = Depends(get_db),
):
    try:
        approver = _get_approver(request, db)
    except HTTPException as exc:
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})

    leave = db.query(models.Leaves).filter(models.Leaves.id == leave_id).first()
    if not leave:
        return JSONResponse(status_code=404, content={"message": "신청 건을 찾을 수 없습니다."})

    try:
        _validate_approvable_leave(approver, leave, db)
    except HTTPException as exc:
        return JSONResponse(status_code=exc.status_code, content={"message": exc.detail})

    try:
        transition = apply_leave_status_transition(
            leave=leave, status_value="REJECTED", rejection_reason=rejection_reason
        )
    except LeaveStatusTransitionError as exc:
        return JSONResponse(status_code=400, content={"message": str(exc)})

    db.add(
        models.AuditLogs(
            actor_id=approver.user_id,
            action="REJECT_LEAVE",
            target_info=f"Leave:{leave_id}",
            old_data=transition.audit_old_data,
            new_data=transition.audit_new_data,
        )
    )
    db.commit()
    return JSONResponse(status_code=200, content={"message": "반려되었습니다."})

