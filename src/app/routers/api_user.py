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
    
    if user.is_admin:
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
    used_hours = sum(float(leave.snapshot_deduction_hours or 0) for leave in yearly_leaves if leave.status != "CANCELED")
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
    
    return _templates(request).TemplateResponse(request=request, name="user_dashboard.html", context={
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
        "year_options": year_options
        ,"time_granularity_minutes": time_granularity_minutes
        ,"lunch_start_minute": lunch_start_minute
        ,"lunch_end_minute": lunch_end_minute
        ,"work_start_minute": work_start_minute
        ,"work_end_minute": work_end_minute
        ,"time_options": time_options
    })

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
            if existing.snapshot_start_min is None or existing.snapshot_end_min is None:
                continue
            if selected.start_min < existing.snapshot_end_min and selected.end_min > existing.snapshot_start_min:
                return JSONResponse(
                    status_code=400,
                    content={"message": "기존 신청 내역과 시간이 겹치는 시간대는 신청할 수 없습니다."}
                )

    current_day_hours = sum(float(l.snapshot_deduction_hours or 0) for l in daily_leaves if l.status != "CANCELED")
    requested_hours = sum(float(s.deduction_hours or 0) for s in resolved_snapshots)
    if current_day_hours + requested_hours > 8:
        return JSONResponse(status_code=400, content={"message": "하루 최대 8시간을 초과하여 연차를 신청할 수 없습니다."})

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
