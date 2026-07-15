from datetime import datetime
from fastapi import APIRouter, Depends, Request, Form, status
from fastapi.responses import HTMLResponse, JSONResponse
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError

from src.app import models, utils
from src.app.database import get_db, DB_PATH
from src.app.dependencies import get_current_admin
from src.app.services import admin_service
from src.app.services.leave_policy import (
    ALLOWED_TIME_GRANULARITIES,
    get_system_settings,
)
from src.app.services.ops import create_sqlite_backup

page_router = APIRouter()
api_router = APIRouter()

def _templates(request: Request):
    return request.app.state.templates

def _ensure_system_setting(db: Session) -> models.SystemSettings:
    setting = db.query(models.SystemSettings).first()
    if not setting:
        setting = models.SystemSettings(
            is_approval_required=False,
            time_granularity_minutes=60,
            work_start_minute=9 * 60,
            work_end_minute=18 * 60,
            lunch_start_minute=12 * 60,
            lunch_end_minute=13 * 60,
            product_display_name="SHIM",
            product_nav_short="",
            brand_initial="S",
        )
        db.add(setting)
        db.commit()
        db.refresh(setting)
    if not getattr(setting, "time_granularity_minutes", None):
        setting.time_granularity_minutes = 60
    if not getattr(setting, "work_start_minute", None):
        setting.work_start_minute = 9 * 60
    if not getattr(setting, "work_end_minute", None):
        setting.work_end_minute = 18 * 60
    if setting.work_end_minute <= setting.work_start_minute:
        setting.work_start_minute = 9 * 60
        setting.work_end_minute = 18 * 60
    if setting.work_start_minute % 30 != 0:
        setting.work_start_minute = (setting.work_start_minute // 30) * 30
    if setting.work_end_minute % 30 != 0:
        setting.work_end_minute = ((setting.work_end_minute + 29) // 30) * 30
    if setting.work_end_minute > 24 * 60:
        setting.work_end_minute = 24 * 60
    if setting.work_end_minute <= setting.work_start_minute:
        setting.work_start_minute = 9 * 60
        setting.work_end_minute = 18 * 60
    db.commit()
    db.refresh(setting)
    return setting


@api_router.get("/settings/approval")
def get_approval_setting(request: Request, db: Session = Depends(get_db), admin: models.Users = Depends(get_current_admin)):
    setting = _ensure_system_setting(db)
    return JSONResponse(
        status_code=200,
        content={
            "is_approval_required": setting.is_approval_required,
            "time_granularity_minutes": setting.time_granularity_minutes,
            "work_start_minute": setting.work_start_minute,
            "work_end_minute": setting.work_end_minute,
            "lunch_start_minute": setting.lunch_start_minute,
            "lunch_end_minute": setting.lunch_end_minute,
            "product_display_name": getattr(setting, "product_display_name", None) or "SHIM",
            "product_nav_short": getattr(setting, "product_nav_short", None) or "",
            "brand_initial": getattr(setting, "brand_initial", None) or "S",
            "team_calendar_visible": bool(getattr(setting, "team_calendar_visible", True)),
            "company_calendar_visible": bool(getattr(setting, "company_calendar_visible", False)),
        },
    )


BRANDING_FIELD_MAX = 120
BRANDING_NAV_SHORT_MAX = 80
BRANDING_BADGE_MAX = 24


@api_router.post("/settings/branding")
def set_branding_setting(
    request: Request,
    product_display_name: str = Form(...),
    product_nav_short: str = Form(""),
    brand_initial: str = Form(""),
    db: Session = Depends(get_db),
    admin: models.Users = Depends(get_current_admin),
):
    display = (product_display_name or "").strip()
    nav_short = (product_nav_short or "").strip()
    initial_raw = (brand_initial or "").strip()[:BRANDING_BADGE_MAX]

    if not display or len(display) > BRANDING_FIELD_MAX:
        return JSONResponse(status_code=400, content={"message": "공식 프로젝트 이름은 1~120자로 입력해 주세요."})
    if len(nav_short) > BRANDING_NAV_SHORT_MAX:
        return JSONResponse(status_code=400, content={"message": f"상단 바 짧은 이름은 {BRANDING_NAV_SHORT_MAX}자 이하로 입력해 주세요."})

    initial = initial_raw
    if not initial:
        initial = (display[:1] if display else "L") or "L"

    setting = _ensure_system_setting(db)
    old_data = (
        f"display={setting.product_display_name};"
        f"nav_short={setting.product_nav_short};"
        f"initial={setting.brand_initial}"
    )
    setting.product_display_name = display
    setting.product_nav_short = nav_short
    setting.brand_initial = initial
    new_data = f"display={display};nav_short={nav_short};initial={initial}"

    db.add(
        models.AuditLogs(
            actor_id=admin.user_id,
            action="UPDATE_BRANDING_SETTING",
            target_info="SystemSettings",
            old_data=old_data,
            new_data=new_data,
        )
    )
    try:
        db.commit()
    except SQLAlchemyError as e:
        db.rollback()
        return JSONResponse(status_code=500, content={"message": utils.format_db_error_message(e)})
    get_system_settings(db, force_reload=True)
    return JSONResponse(status_code=200, content={"message": "브랜딩 설정이 저장되었습니다."})


@api_router.post("/settings/calendar-scope")
def set_calendar_scope_setting(
    request: Request,
    scope: str = Form(...),
    db: Session = Depends(get_db),
    admin: models.Users = Depends(get_current_admin),
):
    if scope not in ("none", "team", "company"):
        return JSONResponse(status_code=400, content={"detail": "Invalid scope value"})

    setting = _ensure_system_setting(db)

    old_team = bool(getattr(setting, "team_calendar_visible", True))
    old_company = bool(getattr(setting, "company_calendar_visible", False))
    if old_company:
        old_scope = "company"
    elif old_team:
        old_scope = "team"
    else:
        old_scope = "none"

    if scope == "none":
        setting.team_calendar_visible = False
        setting.company_calendar_visible = False
    elif scope == "team":
        setting.team_calendar_visible = True
        setting.company_calendar_visible = False
    elif scope == "company":
        setting.team_calendar_visible = True
        setting.company_calendar_visible = True

    db.add(
        models.AuditLogs(
            actor_id=admin.user_id,
            action="UPDATE_CALENDAR_SCOPE_SETTING",
            target_info="SystemSettings",
            old_data=old_scope,
            new_data=scope,
        )
    )
    try:
        db.commit()
    except SQLAlchemyError as e:
        db.rollback()
        return JSONResponse(status_code=500, content={"message": utils.format_db_error_message(e)})
    get_system_settings(db, force_reload=True)
    return JSONResponse(status_code=200, content={"message": "캘린더 공유 범위 설정이 변경되었습니다."})


@api_router.post("/settings/approval")
def set_approval_setting(
    request: Request,
    is_approval_required: bool = Form(...),
    db: Session = Depends(get_db),
    admin: models.Users = Depends(get_current_admin),
):
    setting = _ensure_system_setting(db)
    setting.is_approval_required = is_approval_required
    db.add(
        models.AuditLogs(
            actor_id=admin.user_id,
            action="UPDATE_APPROVAL_SETTING",
            target_info="SystemSettings",
            old_data="",
            new_data=str(is_approval_required),
        )
    )
    try:
        db.commit()
    except SQLAlchemyError as e:
        db.rollback()
        return JSONResponse(status_code=500, content={"message": utils.format_db_error_message(e)})
    get_system_settings(db, force_reload=True)
    return JSONResponse(status_code=200, content={"message": "승인 설정이 변경되었습니다."})


@api_router.post("/settings/time-policy")
def set_time_policy(
    request: Request,
    time_granularity_minutes: int = Form(...),
    work_start_minute: int = Form(...),
    work_end_minute: int = Form(...),
    lunch_start_minute: int = Form(-1),
    lunch_end_minute: int = Form(-1),
    db: Session = Depends(get_db),
    admin: models.Users = Depends(get_current_admin),
):
    if time_granularity_minutes not in ALLOWED_TIME_GRANULARITIES:
        return JSONResponse(status_code=400, content={"message": "시간 단위는 30/60/120분만 허용됩니다."})
    if work_start_minute < 0 or work_start_minute > 1439 or work_end_minute < 1 or work_end_minute > 1440:
        return JSONResponse(status_code=400, content={"message": "업무시간 값이 올바르지 않습니다."})
    if work_start_minute % 30 != 0 or work_end_minute % 30 != 0:
        return JSONResponse(status_code=400, content={"message": "업무시간은 30분 단위로 설정해 주세요."})
    if work_end_minute <= work_start_minute:
        return JSONResponse(status_code=400, content={"message": "업무 종료 시간은 시작 시간보다 늦어야 합니다."})

    normalized_lunch_start = None if lunch_start_minute < 0 else lunch_start_minute
    normalized_lunch_end = None if lunch_end_minute < 0 else lunch_end_minute
    if (normalized_lunch_start is None) != (normalized_lunch_end is None):
        return JSONResponse(status_code=400, content={"message": "점심시간 제외는 시작/종료를 함께 입력해야 합니다."})
    if normalized_lunch_start is not None:
        if normalized_lunch_start < 0 or normalized_lunch_start > 1439 or normalized_lunch_end < 0 or normalized_lunch_end > 1439:
            return JSONResponse(status_code=400, content={"message": "점심시간 설정 값이 올바르지 않습니다."})
        if normalized_lunch_end <= normalized_lunch_start:
            return JSONResponse(status_code=400, content={"message": "점심시간 종료는 시작보다 늦어야 합니다."})

    setting = _ensure_system_setting(db)
    old_data = (
        f"granularity={setting.time_granularity_minutes};"
        f"work={setting.work_start_minute}-{setting.work_end_minute};"
        f"lunch={setting.lunch_start_minute}-{setting.lunch_end_minute}"
    )
    setting.time_granularity_minutes = time_granularity_minutes
    setting.work_start_minute = work_start_minute
    setting.work_end_minute = work_end_minute
    setting.lunch_start_minute = normalized_lunch_start
    setting.lunch_end_minute = normalized_lunch_end
    new_data = (
        f"granularity={setting.time_granularity_minutes};"
        f"work={setting.work_start_minute}-{setting.work_end_minute};"
        f"lunch={setting.lunch_start_minute}-{setting.lunch_end_minute}"
    )

    db.add(
        models.AuditLogs(
            actor_id=admin.user_id,
            action="UPDATE_TIME_POLICY_SETTING",
            target_info="SystemSettings",
            old_data=old_data,
            new_data=new_data,
        )
    )
    try:
        db.commit()
    except SQLAlchemyError as e:
        db.rollback()
        return JSONResponse(status_code=500, content={"message": utils.format_db_error_message(e)})
    get_system_settings(db, force_reload=True)
    return JSONResponse(status_code=200, content={"message": "시간 단위/점심시간 정책이 저장되었습니다."})


@api_router.post("/ops/backup")
def run_backup(request: Request, db: Session = Depends(get_db), admin: models.Users = Depends(get_current_admin)):
    backup_path = create_sqlite_backup(DB_PATH, DB_PATH.parent / "backup")
    db.add(
        models.AuditLogs(
            actor_id=admin.user_id,
            action="MANUAL_DB_BACKUP",
            target_info="Database",
            old_data="",
            new_data=str(backup_path.name),
        )
    )
    db.commit()
    return JSONResponse(status_code=200, content={"message": f"백업이 생성되었습니다: {backup_path.name}"})


@page_router.get("/master", response_class=HTMLResponse)
def admin_master(request: Request, db: Session = Depends(get_db), admin: models.Users = Depends(get_current_admin)):
    setting = _ensure_system_setting(db)
    is_approval_required = bool(setting.is_approval_required) if setting else False
    return _templates(request).TemplateResponse(
        request=request,
        name="admin_master.html",
        context={
            "admin": admin,
            "current_year": utils.get_business_now().year,
            "is_approval_required": is_approval_required,
            "time_granularity_minutes": int(getattr(setting, "time_granularity_minutes", 60) or 60),
            "work_start_minute": int(getattr(setting, "work_start_minute", 9 * 60) or (9 * 60)),
            "work_end_minute": int(getattr(setting, "work_end_minute", 18 * 60) or (18 * 60)),
            "lunch_start_minute": getattr(setting, "lunch_start_minute", None),
            "lunch_end_minute": getattr(setting, "lunch_end_minute", None),
            "half_hour_options": utils.build_half_hour_options(),
            "team_calendar_visible": bool(getattr(setting, "team_calendar_visible", True)),
            "company_calendar_visible": bool(getattr(setting, "company_calendar_visible", False)),
        },
    )
