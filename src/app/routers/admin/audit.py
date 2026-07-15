from datetime import datetime
from urllib.parse import urlencode
import io

from fastapi import APIRouter, Depends, Request, HTTPException
from fastapi.responses import HTMLResponse, StreamingResponse
from sqlalchemy.orm import Session
from openpyxl import Workbook

from src.app import models, utils
from src.app.database import get_db
from src.app.dependencies import get_current_admin
from src.app.services import admin_service

page_router = APIRouter()
api_router = APIRouter()

def _templates(request: Request):
    return request.app.state.templates

AUDIT_ACTION_LABELS = {
    "CREATE_USER": "신규 사원 등록",
    "UPDATE_USER_INFO": "사원 정보 수정",
    "DELETE_USER": "사원 계정 삭제",
    "HARD_DELETE_USER": "사원 정보 영구 삭제",
    "RESET_PASSWORD": "사원 비밀번호 초기화",
    "TOGGLE_USER_ACTIVE": "사원 활성 상태 변경",
    "UPDATE_USER_LEAVE_DAYS": "연차 일수 수정",
    "BULK_UPDATE_USER_LEAVE_DAYS": "연차 일수 일괄 수정",
    "UPDATE_APPROVAL_SETTING": "승인 워크플로우 설정 변경",
    "UPDATE_TEAM_CALENDAR_SETTING": "팀 캘린더 공유 설정 변경",
    "UPDATE_COMPANY_CALENDAR_SETTING": "전사 캘린더 공유 설정 변경",
    "UPDATE_CALENDAR_SCOPE_SETTING": "캘린더 공유 범위 변경",
    "UPDATE_TIME_POLICY_SETTING": "시간 정책 변경",
    "UPDATE_BRANDING_SETTING": "브랜딩 설정 변경",
    "MANUAL_DB_BACKUP": "수동 DB 백업",
    "CREATE_HOLIDAY": "공휴일 등록",
    "UPDATE_HOLIDAY": "공휴일 정보 수정",
    "DELETE_HOLIDAY": "공휴일 삭제",
    "CHANGE_ADMIN_PASSWORD": "관리자 비밀번호 변경",
    "CHANGE_PASSWORD": "사용자 비밀번호 변경",
    "DELETE_LEAVE": "연차 신청 삭제",
    "UPDATE_LEAVE_STATUS": "결재 상태 변경",
    "APPROVE_LEAVE": "연차 승인(팀장/PM)",
    "REJECT_LEAVE": "연차 반려(팀장/PM)",
    "APPLY_LEAVE_BULK": "다수일 연차 일괄 신청",
    "UPDATE_LEAVE_TYPE": "휴가 유형 정정(연차↔출장/공가)",
}

def get_audit_action_label(action: str) -> str:
    if not action:
        return ""
    label = AUDIT_ACTION_LABELS.get(action)
    if not label and action.startswith("SEED_KR_HOLIDAYS_"):
        year_part = action.replace("SEED_KR_HOLIDAYS_", "")
        return f"{year_part}년 공휴일 자동 생성"
    return label or action

def get_audit_target_label(target_info: str) -> str:
    raw_target = (target_info or "").strip()
    if not raw_target:
        return ""

    target = raw_target
    if target.startswith("User:"):
        target = target.replace("User:", "사원:")
    elif target.startswith("Admin:"):
        target = target.replace("Admin:", "관리자:")
    elif target.startswith("Holiday:"):
        target = target.replace("Holiday:", "공휴일:")
    elif target.startswith("Leave:"):
        if "(" in target and ")" in target:
            parts = target.replace("Leave:", "").split(" (", 1)
            leave_id_part = parts[0]
            detail_part = parts[1].replace(")", "")
            target = f"연차신청:{detail_part} [ID:{leave_id_part}]"
        else:
            target = target.replace("Leave:", "연차신청(ID:") + ")"
    elif target.startswith("HolidaySeed:"):
        target = target.replace("HolidaySeed:", "") + "년 공휴일 생성"
    elif target == "SystemSettings":
        target = "시스템 설정"
    elif target == "Database":
        target = "데이터베이스"
    elif target.startswith("Scope:"):
        parts = {}
        for part in target.split(","):
            if ":" in part:
                k, v = part.split(":", 1)
                parts[k.strip()] = v.strip()
        scope_val = parts.get("Scope", "all")
        scope_ko = {"all": "전체", "active": "활성 사원", "inactive": "비활성 사원"}.get(scope_val, scope_val)
        year_val = parts.get("Year", "")
        count_val = parts.get("Count", "")
        target = f"범위:{scope_ko}, 연도:{year_val}, 건수:{count_val}"
    elif target.startswith("Leaves for "):
        dates_str = target.replace("Leaves for ", "")
        target = f"다수일 연차 신청: {dates_str}"

    return target


@page_router.get("/audit", response_class=HTMLResponse)
def admin_audit_logs(
    request: Request,
    actor_id: str = "",
    action: str = "",
    start_date: str = "",
    end_date: str = "",
    page: int = 1,
    db: Session = Depends(get_db),
    admin: models.Users = Depends(get_current_admin),
):
    per_page = 50
    s_date = None
    e_date = None
    if start_date:
        try:
            s_date = datetime.strptime(start_date, "%Y-%m-%d").date()
        except ValueError:
            pass
    if end_date:
        try:
            e_date = datetime.strptime(end_date, "%Y-%m-%d").date()
        except ValueError:
            pass

    if s_date and e_date and (e_date - s_date).days > 90:
        users = db.query(models.Users).filter(models.Users.is_active == True).order_by(models.Users.user_name).all()
        return _templates(request).TemplateResponse(
            request=request,
            name="admin_audit.html",
            context={
                "admin": admin,
                "logs": [],
                "users": users,
                "actor_id": actor_id,
                "action": action,
                "start_date": start_date,
                "end_date": end_date,
                "page": 1,
                "total_pages": 0,
                "total_count": 0,
                "current_year": utils.get_business_now().year,
                "export_query": "",
                "error_msg": "조회 기간은 최대 90일을 초과할 수 없습니다.",
            },
        )

    query = admin_service.get_audit_logs_query(
        db=db,
        actor_id=actor_id.strip(),
        action=action.strip(),
        start_date=s_date,
        end_date=e_date,
    )

    total_count = query.count()
    total_pages = (total_count + per_page - 1) // per_page
    if page > total_pages and total_pages > 0:
        page = total_pages
    if page < 1:
        page = 1

    logs = (
        query.order_by(models.AuditLogs.timestamp.desc())
        .offset((page - 1) * per_page)
        .limit(per_page)
        .all()
    )

    users = db.query(models.Users).filter(models.Users.is_active == True).order_by(models.Users.user_name).all()

    for log in logs:
        log.action_label = get_audit_action_label(log.action)
        log.target_label = get_audit_target_label(log.target_info) or (log.target_info or "")

    export_q = {
        "actor_id": actor_id,
        "action": action,
        "start_date": start_date,
        "end_date": end_date,
    }

    return _templates(request).TemplateResponse(
        request=request,
        name="admin_audit.html",
        context={
            "admin": admin,
            "logs": logs,
            "users": users,
            "actor_id": actor_id,
            "action": action,
            "start_date": start_date,
            "end_date": end_date,
            "page": page,
            "total_pages": total_pages,
            "total_count": total_count,
            "current_year": utils.get_business_now().year,
            "export_query": urlencode({k: v for k, v in export_q.items() if v}),
        },
    )


@page_router.get("/audit/export")
def admin_audit_export(
    actor_id: str = "",
    action: str = "",
    start_date: str = "",
    end_date: str = "",
    db: Session = Depends(get_db),
    admin: models.Users = Depends(get_current_admin),
):
    s_date = None
    e_date = None
    if start_date:
        try:
            s_date = datetime.strptime(start_date, "%Y-%m-%d").date()
        except ValueError:
            pass
    if end_date:
        try:
            e_date = datetime.strptime(end_date, "%Y-%m-%d").date()
        except ValueError:
            pass

    if s_date and e_date and (e_date - s_date).days > 90:
        raise HTTPException(status_code=400, detail="조회 기간은 최대 90일을 초과할 수 없습니다.")

    query = admin_service.get_audit_logs_query(
        db=db,
        actor_id=actor_id.strip(),
        action=action.strip(),
        start_date=s_date,
        end_date=e_date,
    )
    logs = query.order_by(models.AuditLogs.timestamp.desc()).all()

    wb = Workbook()
    ws = wb.active
    ws.title = "Audit Logs"
    headers = ["시각", "수행자(ID)", "수행자(이름)", "수행자 소속", "액션(코드)", "액션(내용)", "대상 정보", "이전 데이터", "이후 데이터"]
    ws.append(headers)

    for log in logs:
        actor_name = log.actor.user_name if log.actor else (log.actor_name if log.actor_name else "System")
        if log.actor_department:
            actor_dept = log.actor_department
        elif log.actor:
            actor_dept = f"{log.actor.company or ''} {log.actor.team or ''}".strip()
        else:
            actor_dept = ""
        action_label = get_audit_action_label(log.action)
        target = get_audit_target_label(log.target_info) or (log.target_info or "")

        ws.append(
            [
                utils.format_datetime_business(log.timestamp, "%Y-%m-%d %H:%M:%S"),
                log.actor_id or "",
                actor_name,
                actor_dept,
                log.action,
                action_label,
                target,
                log.old_data,
                log.new_data,
            ]
        )

    out = io.BytesIO()
    wb.save(out)
    wb.close()
    out.seek(0)

    if s_date and e_date:
        filename = f"audit_{s_date.strftime('%Y%m%d')}_{e_date.strftime('%Y%m%d')}.xlsx"
    else:
        filename = f"audit_logs_{utils.get_business_now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    return StreamingResponse(
        out,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )
