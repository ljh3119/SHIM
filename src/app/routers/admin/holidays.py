from datetime import datetime, date as date_cls
from fastapi import APIRouter, Depends, Request, Form, status
from fastapi.responses import HTMLResponse, JSONResponse
from sqlalchemy import extract
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError

from src.app import models, utils
from src.app.database import get_db
from src.app.dependencies import get_current_admin

page_router = APIRouter()
api_router = APIRouter()

def _templates(request: Request):
    return request.app.state.templates

@page_router.get("/holidays", response_class=HTMLResponse)
def admin_holidays(request: Request, year: int = None, db: Session = Depends(get_db), admin: models.Users = Depends(get_current_admin)):
    now = utils.get_business_now()
    current_year = year if year else now.year

    month_start = date_cls(current_year, 1, 1)
    month_end = date_cls(current_year, 12, 31)
    holidays = db.query(models.Holidays).filter(
        models.Holidays.date >= month_start,
        models.Holidays.date <= month_end
    ).order_by(models.Holidays.date.asc()).all()
    holiday_year_rows = db.query(extract('year', models.Holidays.date)).distinct().all()
    holiday_years = [int(row[0]) for row in holiday_year_rows if row[0] is not None]
    year_options = utils.build_year_options(now.year, holiday_years)

    return _templates(request).TemplateResponse(request=request, name="admin_holidays.html", context={
        "admin": admin,
        "holidays": holidays,
        "selected_year": current_year,
        "current_year": now.year,
        "year_options": year_options
    })

@api_router.post("/holiday/create")
def create_holiday(
    request: Request,
    holiday_name: str = Form(...),
    holiday_date: str = Form(...),
    db: Session = Depends(get_db),
    admin: models.Users = Depends(get_current_admin),
):
    holiday_name = holiday_name.strip()
    if not holiday_name:
        return JSONResponse(status_code=400, content={"message": "공휴일 이름을 입력해 주세요."})

    try:
        parsed_date = datetime.strptime(holiday_date, "%Y-%m-%d").date()
    except ValueError:
        return JSONResponse(status_code=400, content={"message": "날짜 형식이 올바르지 않습니다."})

    exist = db.query(models.Holidays).filter(models.Holidays.date == parsed_date).first()
    if exist:
        return JSONResponse(status_code=400, content={"message": "해당 날짜에는 이미 공휴일이 등록되어 있습니다."})

    new_holiday = models.Holidays(name=holiday_name, date=parsed_date)
    db.add(new_holiday)

    audit = models.AuditLogs(
        actor_id=admin.user_id,
        action="CREATE_HOLIDAY",
        target_info=f"Holiday:{parsed_date}",
        old_data="None",
        new_data=holiday_name
    )
    db.add(audit)
    try:
        db.commit()
    except SQLAlchemyError as e:
        db.rollback()
        return JSONResponse(status_code=500, content={"message": utils.format_db_error_message(e)})

    return JSONResponse(status_code=200, content={"message": "공휴일이 등록되었습니다."})

@api_router.post("/holiday/update")
def update_holiday(
    request: Request,
    holiday_id: int = Form(...),
    holiday_name: str = Form(...),
    holiday_date: str = Form(...),
    db: Session = Depends(get_db),
    admin: models.Users = Depends(get_current_admin),
):
    holiday = db.query(models.Holidays).filter(models.Holidays.id == holiday_id).first()
    if not holiday:
        return JSONResponse(status_code=404, content={"message": "공휴일 정보를 찾을 수 없습니다."})

    holiday_name = holiday_name.strip()
    if not holiday_name:
        return JSONResponse(status_code=400, content={"message": "공휴일 이름을 입력해 주세요."})

    try:
        parsed_date = datetime.strptime(holiday_date, "%Y-%m-%d").date()
    except ValueError:
        return JSONResponse(status_code=400, content={"message": "날짜 형식이 올바르지 않습니다."})

    duplicate = db.query(models.Holidays).filter(
        models.Holidays.date == parsed_date,
        models.Holidays.id != holiday_id
    ).first()
    if duplicate:
        return JSONResponse(status_code=400, content={"message": "해당 날짜에는 이미 다른 공휴일이 등록되어 있습니다."})

    old_data = f"{holiday.date}:{holiday.name}"
    holiday.name = holiday_name
    holiday.date = parsed_date

    audit = models.AuditLogs(
        actor_id=admin.user_id,
        action="UPDATE_HOLIDAY",
        target_info=f"Holiday:{holiday_id}",
        old_data=old_data,
        new_data=f"{parsed_date}:{holiday_name}"
    )
    db.add(audit)
    try:
        db.commit()
    except SQLAlchemyError as e:
        db.rollback()
        return JSONResponse(status_code=500, content={"message": utils.format_db_error_message(e)})

    return JSONResponse(status_code=200, content={"message": "공휴일이 수정되었습니다."})

@api_router.post("/holiday/delete")
def delete_holiday(
    request: Request,
    holiday_id: int = Form(...),
    db: Session = Depends(get_db),
    admin: models.Users = Depends(get_current_admin),
):
    holiday = db.query(models.Holidays).filter(models.Holidays.id == holiday_id).first()
    if not holiday:
        return JSONResponse(status_code=404, content={"message": "공휴일 정보를 찾을 수 없습니다."})

    old_data = f"{holiday.date}:{holiday.name}"
    db.delete(holiday)

    audit = models.AuditLogs(
        actor_id=admin.user_id,
        action="DELETE_HOLIDAY",
        target_info=f"Holiday:{holiday_id}",
        old_data=old_data,
        new_data="DELETED"
    )
    db.add(audit)
    try:
        db.commit()
    except SQLAlchemyError as e:
        db.rollback()
        return JSONResponse(status_code=500, content={"message": utils.format_db_error_message(e)})

    return JSONResponse(status_code=200, content={"message": "공휴일이 삭제되었습니다."})
