from datetime import datetime
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Request, Form, status
from fastapi.responses import HTMLResponse, JSONResponse
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError

from src.app import models, auth, utils
from src.app.database import get_db
from src.app.dependencies import get_current_admin
from src.app.services import admin_service
from src.app.constants import VALID_ROLES

page_router = APIRouter()
api_router = APIRouter()

def _templates(request: Request):
    return request.app.state.templates

@api_router.post("/change-password")
def admin_change_password(
    request: Request,
    current_password: str = Form(...),
    new_password: str = Form(...),
    db: Session = Depends(get_db),
    admin: models.Users = Depends(get_current_admin),
):
    if not auth.verify_password(current_password, admin.password):
        return JSONResponse(status_code=400, content={"message": "현재 비밀번호가 일치하지 않습니다."})

    validation_error = utils.validate_password_strength(new_password)
    if validation_error:
        return JSONResponse(status_code=400, content={"message": validation_error})

    admin.password = auth.get_password_hash(new_password)
    admin.token_version += 1
    audit = models.AuditLogs(
        actor_id=admin.user_id,
        action="CHANGE_ADMIN_PASSWORD",
        target_info=f"Admin:{admin.user_id}",
        old_data="*****",
        new_data="*****"
    )
    db.add(audit)
    try:
        db.commit()
    except SQLAlchemyError as e:
        db.rollback()
        return JSONResponse(status_code=500, content={"message": utils.format_db_error_message(e)})

    return JSONResponse(status_code=200, content={"message": "비밀번호가 성공적으로 변경되었습니다."})


@page_router.get("/users", response_class=HTMLResponse)
def admin_users(
    request: Request,
    filter: str = "all",
    year: int = None,
    sort_key: str = "role",
    sort_dir: str = "asc",
    q: str = "",
    db: Session = Depends(get_db),
    admin: models.Users = Depends(get_current_admin),
):
    query = db.query(models.Users)
    if filter == "active":
        query = query.filter(models.Users.is_active == True)
    elif filter == "inactive":
        query = query.filter(models.Users.is_active == False)
        
    users = query.all()

    # 인메모리 검색 적용 (Fernet 복호화 및 한글 초성 매칭)
    if q and q.strip():
        users = utils.search_users_stateless(users, q)

    sort_key_effective = sort_key if sort_key in {"user_name", "user_id", "company", "team", "leave_days", "role"} else "role"
    sort_dir_effective = "desc" if sort_dir == "desc" else "asc"
    now_year = utils.get_local_now().year
    selected_year = year if year else now_year
    leave_year_rows = db.query(models.Leaves.year).distinct().all()
    leave_years = [row[0] for row in leave_year_rows]
    allocation_year_rows = db.query(models.UserYearlyLeaveAllocations.year).distinct().all()
    allocation_years = [row[0] for row in allocation_year_rows]
    year_options = utils.build_year_options(now_year, leave_years + allocation_years)
    allocation_map = admin_service.get_yearly_allocation_map(db, [u.user_id for u in users], selected_year)
    user_leave_days_map = {
        u.user_id: int(allocation_map.get(u.user_id, u.total_leave_hours or 0)) // 8
        for u in users
    }
    def _user_sort_tuple(u: models.Users):
        company_text = (u.company or "").lower()
        team_text = (u.team or "").lower()
        leave_days = user_leave_days_map.get(u.user_id, 0)
        role_priority = {"ADMIN": 0, "PM": 1, "TEAM_LEAD": 2, "STAFF": 3}
        key_map = {
            "user_name": ((u.user_name or "").lower(), (u.user_id or "").lower()),
            "user_id": ((u.user_id or "").lower(), (u.user_name or "").lower()),
            "company": (company_text, (u.user_name or "").lower(), (u.user_id or "").lower()),
            "team": (team_text, (u.user_name or "").lower(), (u.user_id or "").lower()),
            "leave_days": (leave_days, (u.user_name or "").lower(), (u.user_id or "").lower()),
            "role": (role_priority.get(u.role, 9), (u.user_name or "").lower(), (u.user_id or "").lower()),
        }
        return key_map[sort_key_effective]

    active_users = [u for u in users if u.is_active]
    inactive_users = [u for u in users if not u.is_active]

    active_sorted = sorted(active_users, key=_user_sort_tuple, reverse=(sort_dir_effective == "desc"))
    inactive_sorted = sorted(inactive_users, key=_user_sort_tuple, reverse=(sort_dir_effective == "desc"))
    users_sorted = active_sorted + inactive_sorted

    base_q = {"filter": filter, "year": str(selected_year)}
    if q:
        base_q["q"] = q
    sort_urls = {}
    for col in ("user_name", "user_id", "company", "team", "leave_days", "role"):
        next_dir = "desc" if (sort_key_effective == col and sort_dir_effective == "asc") else "asc"
        sort_params = {**base_q, "sort_key": col, "sort_dir": next_dir}
        sort_urls[col] = f"/admin/users?{urlencode(sort_params)}"
    
    return _templates(request).TemplateResponse(request=request, name="admin_users.html", context={
        "admin": admin,
        "users": users_sorted,
        "current_filter": filter,
        "sort_key": sort_key_effective,
        "sort_dir": sort_dir_effective,
        "sort_urls": sort_urls,
        "selected_year": selected_year,
        "year_options": year_options,
        "user_leave_days_map": user_leave_days_map,
        "q": q
    })


@api_router.post("/user/toggle")
def toggle_user_active(
    request: Request,
    target_user_id: str = Form(...),
    db: Session = Depends(get_db),
    admin: models.Users = Depends(get_current_admin),
):
    user = db.query(models.Users).filter(models.Users.user_id == target_user_id).first()
    if not user:
        return JSONResponse(status_code=404, content={"message": "User not found"})
        
    if user.user_id == admin.user_id:
        return JSONResponse(status_code=400, content={"message": "본인 계정은 비활성화 할 수 없습니다."})

    if user.role == "ADMIN":
        return JSONResponse(status_code=400, content={"message": "관리자 계정은 비활성화 할 수 없습니다."})
        
    old_status = user.is_active
    user.is_active = not user.is_active
    user.token_version += 1
    
    canceled_count = 0
    if not user.is_active:
        today_str = utils.get_local_today()
        today = datetime.strptime(today_str, "%Y-%m-%d").date()
        future_leaves = db.query(models.Leaves).filter(
            models.Leaves.user_id == target_user_id,
            models.Leaves.date >= today,
            models.Leaves.status.notin_(["CANCELED", "REJECTED"])
        ).all()
        canceled_count = len(future_leaves)
        for leave in future_leaves:
            leave.status = "CANCELED"
            
    audit = models.AuditLogs(
        actor_id=admin.user_id,
        action="TOGGLE_USER_ACTIVE",
        target_info=f"User:{target_user_id}",
        old_data=str(old_status),
        new_data=str(user.is_active)
    )
    db.add(audit)
    try:
        db.commit()
    except SQLAlchemyError as e:
        db.rollback()
        return JSONResponse(status_code=500, content={"message": utils.format_db_error_message(e)})
    msg = f"사원 비활성화 완료 (미래 연차 {canceled_count}건 취소됨)" if not user.is_active else "사원이 활성화되었습니다."
    return JSONResponse(status_code=200, content={"message": msg})


@api_router.post("/user/reset-password")
def reset_password(
    request: Request,
    target_user_id: str = Form(...),
    db: Session = Depends(get_db),
    admin: models.Users = Depends(get_current_admin),
):
    user = db.query(models.Users).filter(models.Users.user_id == target_user_id).first()
    if not user:
        return JSONResponse(status_code=404, content={"message": "User not found"})
        
    user.password = auth.get_password_hash("0000")
    user.token_version += 1
    
    audit = models.AuditLogs(
        actor_id=admin.user_id,
        action="RESET_PASSWORD",
        target_info=f"User:{target_user_id}",
        old_data="*****",
        new_data="*****"
    )
    db.add(audit)
    try:
        db.commit()
    except SQLAlchemyError as e:
        db.rollback()
        return JSONResponse(status_code=500, content={"message": utils.format_db_error_message(e)})
    return JSONResponse(status_code=200, content={"message": "비밀번호가 '0000'으로 초기화되었습니다."})


@api_router.post("/user/update")
def update_user(
    request: Request,
    target_user_id: str = Form(...),
    user_name: str = Form(...),
    company: str = Form(""),
    team: str = Form(""),
    role: str = Form("STAFF"),
    position: str = Form(""),
    is_active: bool = Form(True),
    db: Session = Depends(get_db),
    admin: models.Users = Depends(get_current_admin),
):
    user = db.query(models.Users).filter(models.Users.user_id == target_user_id).first()
    if not user:
        return JSONResponse(status_code=404, content={"message": "User not found"})

    if user.role == "ADMIN" and is_active is False:
        return JSONResponse(
            status_code=400, content={"message": "관리자 계정은 비활성화 할 수 없습니다."}
        )

    role_value = (role or "STAFF").strip().upper()
    if role_value not in VALID_ROLES:
        role_value = "STAFF"

    if role_value == "ADMIN" and user.role != "ADMIN":
        return JSONResponse(
            status_code=400, content={"message": "관리자 역할은 직접 지정할 수 없습니다."}
        )

    old_data = (
        f"name={user.user_name};company={user.company};team={user.team};"
        f"role={user.role};position={user.position};active={user.is_active}"
    )

    user.user_name = user_name.strip()
    user.company = company.strip() if company else None
    user.team = team.strip() if team else None
    user.role = role_value
    user.position = position.strip() if position else None
    
    was_active = user.is_active
    user.is_active = is_active
    user.token_version += 1

    canceled_count = 0
    if was_active and not user.is_active:
        today_str = utils.get_local_today()
        today = datetime.strptime(today_str, "%Y-%m-%d").date()
        future_leaves = db.query(models.Leaves).filter(
            models.Leaves.user_id == target_user_id,
            models.Leaves.date >= today,
            models.Leaves.status.notin_(["CANCELED", "REJECTED"])
        ).all()
        canceled_count = len(future_leaves)
        for leave in future_leaves:
            leave.status = "CANCELED"

    new_data = (
        f"name={user.user_name};company={user.company};team={user.team};"
        f"role={user.role};position={user.position};active={user.is_active}"
    )

    audit = models.AuditLogs(
        actor_id=admin.user_id,
        action="UPDATE_USER_INFO",
        target_info=f"User:{target_user_id}",
        old_data=old_data,
        new_data=new_data,
    )
    db.add(audit)
    try:
        db.commit()
    except SQLAlchemyError as e:
        db.rollback()
        return JSONResponse(status_code=500, content={"message": utils.format_db_error_message(e)})
    msg = f"사원 정보가 수정되었으며, 사원이 비활성화되었습니다. (미래 연차 {canceled_count}건 취소됨)" if (was_active and not user.is_active) else "사원 정보가 성공적으로 수정되었습니다."
    return JSONResponse(status_code=200, content={"message": msg})


@api_router.post("/user/create")
def create_user(
    request: Request,
    user_id: str = Form(...),
    user_name: str = Form(...),
    company: str = Form(""),
    team: str = Form(""),
    role: str = Form("STAFF"),
    position: str = Form(""),
    total_leave_days: int = Form(15),
    year: int = Form(None),
    db: Session = Depends(get_db),
    admin: models.Users = Depends(get_current_admin),
):
    user_id = user_id.strip()
    if total_leave_days < 0:
        return JSONResponse(status_code=400, content={"message": "연차일수는 0 이상이어야 합니다."})

    role_value = (role or "STAFF").strip().upper()
    if role_value not in VALID_ROLES:
        role_value = "STAFF"
    if role_value == "ADMIN":
        return JSONResponse(status_code=400, content={"message": "관리자 역할은 직접 지정할 수 없습니다."})
    position_value = (position or "").strip()[:60]

    exist = db.query(models.Users).filter(models.Users.user_id == user_id).first()
    if exist:
        return JSONResponse(status_code=400, content={"message": "이미 존재하는 ID입니다."})
        
    target_year = year if year else utils.get_local_now().year
    new_user = models.Users(
        user_id=user_id,
        user_name=user_name,
        company=company,
        team=team,
        total_leave_hours=total_leave_days * 8,
        password=auth.get_password_hash("0000"),
        is_active=True,
        role=role_value,
        position=position_value if position_value else None,
    )
    db.add(new_user)
    db.flush()
    db.add(
        models.UserYearlyLeaveAllocations(
            user_id=user_id,
            year=target_year,
            allocated_hours=total_leave_days * 8
        )
    )
    
    audit = models.AuditLogs(
        actor_id=admin.user_id,
        action="CREATE_USER",
        target_info=f"User:{user_id}",
        old_data="None",
        new_data=f"{user_name};role={role_value}"
    )
    db.add(audit)
    try:
        db.commit()
    except SQLAlchemyError as e:
        db.rollback()
        return JSONResponse(status_code=500, content={"message": utils.format_db_error_message(e)})
    return JSONResponse(status_code=200, content={"message": f"{user_name} 등록 완료! 초기 비번: 0000"})


@api_router.post("/user/update-leave-days")
def update_user_leave_days(
    request: Request,
    target_user_id: str = Form(...),
    total_leave_days: int = Form(...),
    year: int = Form(None),
    db: Session = Depends(get_db),
    admin: models.Users = Depends(get_current_admin),
):
    if total_leave_days < 0:
        return JSONResponse(status_code=400, content={"message": "연차일수는 0 이상이어야 합니다."})

    user = db.query(models.Users).filter(models.Users.user_id == target_user_id).first()
    if not user:
        return JSONResponse(status_code=404, content={"message": "User not found"})

    target_year = year if year else utils.get_local_now().year
    old_hours = user.total_leave_hours
    new_hours = total_leave_days * 8
    allocation = db.query(models.UserYearlyLeaveAllocations).filter(
        models.UserYearlyLeaveAllocations.user_id == target_user_id,
        models.UserYearlyLeaveAllocations.year == target_year
    ).first()
    old_allocated = int(allocation.allocated_hours) if allocation else int(old_hours or 0)
    if allocation:
        allocation.allocated_hours = new_hours
    else:
        db.add(
            models.UserYearlyLeaveAllocations(
                user_id=target_user_id,
                year=target_year,
                allocated_hours=new_hours
            )
        )

    audit = models.AuditLogs(
        actor_id=admin.user_id,
        action="UPDATE_USER_LEAVE_DAYS",
        target_info=f"User:{target_user_id}",
        old_data=f"{target_year}:{old_allocated}h",
        new_data=f"{target_year}:{new_hours}h({total_leave_days}d)"
    )
    db.add(audit)
    try:
        db.commit()
    except SQLAlchemyError as e:
        db.rollback()
        return JSONResponse(status_code=500, content={"message": utils.format_db_error_message(e)})
    return JSONResponse(status_code=200, content={"message": "연차일수가 변경되었습니다."})


@api_router.post("/user/bulk-update-leave-days")
def bulk_update_user_leave_days(
    request: Request,
    total_leave_days: int = Form(...),
    year: int = Form(None),
    filter_scope: str = Form("all"),
    db: Session = Depends(get_db),
    admin: models.Users = Depends(get_current_admin),
):
    if total_leave_days < 0:
        return JSONResponse(status_code=400, content={"message": "연차일수는 0 이상이어야 합니다."})

    target_year = year if year else utils.get_local_now().year
    new_hours = total_leave_days * 8

    q = db.query(models.Users).filter(models.Users.role != "ADMIN")
    if filter_scope == "active":
        q = q.filter(models.Users.is_active == True)
    elif filter_scope == "inactive":
        q = q.filter(models.Users.is_active == False)
    target_users = q.all()

    if not target_users:
        return JSONResponse(status_code=400, content={"message": "일괄지급 대상 사용자가 없습니다."})

    updated_count = 0
    for user in target_users:
        allocation = db.query(models.UserYearlyLeaveAllocations).filter(
            models.UserYearlyLeaveAllocations.user_id == user.user_id,
            models.UserYearlyLeaveAllocations.year == target_year
        ).first()
        if allocation:
            allocation.allocated_hours = new_hours
        else:
            db.add(
                models.UserYearlyLeaveAllocations(
                    user_id=user.user_id,
                    year=target_year,
                    allocated_hours=new_hours
                )
            )
        updated_count += 1

    audit = models.AuditLogs(
        actor_id=admin.user_id,
        action="BULK_UPDATE_USER_LEAVE_DAYS",
        target_info=f"Scope:{filter_scope}, Year:{target_year}, Count:{updated_count}",
        old_data="BULK",
        new_data=f"{new_hours}h({total_leave_days}d)"
    )
    db.add(audit)
    try:
        db.commit()
    except SQLAlchemyError as e:
        db.rollback()
        return JSONResponse(status_code=500, content={"message": utils.format_db_error_message(e)})
    return JSONResponse(
        status_code=200,
        content={"message": f"{target_year}년 연차일수를 {updated_count}명에게 일괄 {total_leave_days}일로 반영했습니다."}
    )


@api_router.post("/user/hard-delete")
def hard_delete_user(
    request: Request,
    target_user_id: str = Form(...),
    db: Session = Depends(get_db),
    admin: models.Users = Depends(get_current_admin),
):
    user = db.query(models.Users).filter(models.Users.user_id == target_user_id).first()
    if not user:
        return JSONResponse(status_code=404, content={"message": "User not found"})
        
    if user.user_id == admin.user_id:
        return JSONResponse(status_code=400, content={"message": "본인 계정은 완전히 삭제할 수 없습니다."})

    if user.role == "ADMIN":
        return JSONResponse(status_code=400, content={"message": "관리자 계정은 삭제할 수 없습니다."})
        
    user_name = user.user_name
    db.delete(user)
    
    audit = models.AuditLogs(
        actor_id=admin.user_id,
        action="HARD_DELETE_USER",
        target_info=f"User:{target_user_id} ({user_name})",
        old_data="EXISTS",
        new_data="DELETED"
    )
    db.add(audit)
    try:
        db.commit()
    except SQLAlchemyError as e:
        db.rollback()
        return JSONResponse(status_code=500, content={"message": utils.format_db_error_message(e)})
    return JSONResponse(status_code=200, content={"message": "사원 계정이 완전히 삭제되었습니다."})
