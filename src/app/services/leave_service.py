from datetime import datetime, date as date_cls
from sqlalchemy.orm import Session
from sqlalchemy import func, text
from sqlalchemy.exc import SQLAlchemyError

from .. import models, utils
from .leave_policy import (
    LeaveInputValidationError,
    build_snapshot_from_timerange,
    resolve_time_policy_setting,
    get_system_settings,
)

def resolve_user_yearly_allocated_hours(db: Session, user: models.Users, year: int) -> int:
    try:
        allocation = db.query(models.UserYearlyLeaveAllocations).filter(
            models.UserYearlyLeaveAllocations.user_id == user.user_id,
            models.UserYearlyLeaveAllocations.year == year
        ).first()
        if allocation:
            return int(allocation.allocated_hours)
    except SQLAlchemyError:
        db.rollback()
    return int(user.total_leave_hours or 0)

def validate_and_apply_leave(
    db: Session,
    user: models.Users,
    date_str: str,
    start_time: str,
    end_time: str,
    is_deductive: bool,
    reason: str,
) -> str:
    # 비차감 신청 시 사유 필수 체크
    if not is_deductive and not (reason and reason.strip()):
        raise LeaveInputValidationError("연차 비차감 신청 시 사유를 입력해 주세요.")

    start_time = (start_time or "").strip()
    end_time = (end_time or "").strip()
    if bool(start_time) != bool(end_time):
        raise LeaveInputValidationError("시작 시간과 종료 시간을 함께 입력해 주세요.")

    # 날짜 목록 파싱
    raw_dates = [d.strip() for d in date_str.split(",") if d.strip()]
    if not raw_dates:
        raise LeaveInputValidationError("신청할 날짜를 입력해 주세요.")


    try:
        # 동시 요청이 같은 검증 결과를 보지 않도록 SQLite 쓰기 예약 잠금을 먼저 획득합니다.
        db.execute(text("BEGIN IMMEDIATE"))
        # 1. 정책 및 데이터 설정 로드
        (
            granularity,
            lunch_start,
            lunch_end,
            work_start,
            work_end,
        ) = resolve_time_policy_setting(db)

        # 날짜들을 미리 datetime.date 객체로 파싱
        parsed_dates = []
        for d_str in raw_dates:
            try:
                parsed_dates.append(datetime.strptime(d_str, "%Y-%m-%d").date())
            except ValueError:
                raise LeaveInputValidationError(f"날짜 형식이 올바르지 않습니다: {d_str}")

        parsed_dates = list(dict.fromkeys(parsed_dates))
        is_multiple = len(parsed_dates) > 1

        # 공휴일 일괄 조회 (N+1 최적화)
        holidays = db.query(models.Holidays).filter(models.Holidays.date.in_(parsed_dates)).all()
        holiday_map = {h.date: h.name for h in holidays}

        # 2. 날짜 필터링 (주말 및 공휴일 체크)
        valid_dates = []
        for req_date in parsed_dates:
            # 단일 신청 시에는 주말/공휴일 즉시 에러
            if not is_multiple:
                if req_date.weekday() >= 5:
                    raise LeaveInputValidationError("주말에는 신청할 수 없습니다.")
                if req_date in holiday_map:
                    raise LeaveInputValidationError(f"공휴일({holiday_map[req_date]})에는 신청할 수 없습니다.")
                valid_dates.append(req_date)
            else:
                # 다중 신청 시에는 주말/공휴일 자동 건너뛰기
                if req_date.weekday() >= 5:
                    continue
                if req_date in holiday_map:
                    continue
                valid_dates.append(req_date)

        if not valid_dates:
            raise LeaveInputValidationError("신청 가능한 영업일이 없습니다.")

        # 시간 지정이 누락되었거나 하루종일 신청 시 설정 기준 시간 자동 매핑
        if not start_time:
            start_hour = work_start // 60
            start_min = work_start % 60
            end_hour = work_end // 60
            end_min = work_end % 60
            start_time = f"{start_hour:02d}:{start_min:02d}"
            end_time = f"{end_hour:02d}:{end_min:02d}"

        # 3. 시간 기반 스냅샷 생성 (공통 스냅샷 생성)
        snapshot = build_snapshot_from_timerange(
            start_time=start_time,
            end_time=end_time,
            granularity_minutes=granularity,
            lunch_start_minute=lunch_start,
            lunch_end_minute=lunch_end,
            work_start_minute=work_start,
            work_end_minute=work_end,
        )

        if snapshot.deduction_hours <= 0:
            raise LeaveInputValidationError("유효한 신청 시간이 아닙니다.")

        # 4. 검증 및 DB 추가 대상 리스트 생성
        yearly_new_deductions = {}
        for req_date in valid_dates:
            yr = req_date.year
            yearly_new_deductions[yr] = yearly_new_deductions.get(yr, 0.0) + snapshot.deduction_hours

        # 점심시간 공제 후 일일 최대 순수 근무 시간 계산
        lunch_minutes = 0
        if lunch_start is not None and lunch_end is not None and lunch_end > lunch_start:
            lunch_minutes = lunch_end - lunch_start
        max_daily_hours = (work_end - work_start - lunch_minutes) / 60.0

        # 개별 날짜별 중복 및 일일 한도 체크 (N+1 쿼리 방지 일괄 조회)
        all_existing_leaves = db.query(models.Leaves).filter(
            models.Leaves.user_id == user.user_id,
            models.Leaves.date.in_(valid_dates),
            models.Leaves.status.notin_(["CANCELED", "REJECTED"])
        ).all()

        existing_by_date = {}
        for el in all_existing_leaves:
            existing_by_date.setdefault(el.date, []).append(el)

        for req_date in valid_dates:
            existing_leaves = existing_by_date.get(req_date, [])

            daily_total = snapshot.deduction_hours
            for el in existing_leaves:
                # 시간대 중복 체크
                if not (snapshot.end_min <= el.snapshot_start_min or snapshot.start_min >= el.snapshot_end_min):
                    raise LeaveInputValidationError(f"{req_date} 날짜에 이미 신청된 시간대와 중복됩니다.")
                daily_total += el.snapshot_deduction_hours

            if daily_total > max_daily_hours + 0.01:
                raise LeaveInputValidationError(f"{req_date} 날짜의 총 신청 시간이 {max_daily_hours}시간을 초과합니다.")

        # 5. 잔여 연차 체크 (is_deductive=True 인 경우만, 연도별 검증)
        if is_deductive:
            for yr, add_hours in yearly_new_deductions.items():
                total_allocated = resolve_user_yearly_allocated_hours(db, user, yr)
                used_hours = db.query(func.sum(models.Leaves.snapshot_deduction_hours)).filter(
                    models.Leaves.user_id == user.user_id,
                    models.Leaves.year == yr,
                    models.Leaves.status.notin_(["CANCELED", "REJECTED"]),
                    models.Leaves.is_deductive == True
                ).scalar() or 0.0

                if used_hours + add_hours > total_allocated:
                    raise LeaveInputValidationError(f"{yr}년도 잔여 연차가 부족합니다.")

        # 6. 상태 결정
        setting = get_system_settings(db)
        is_approval_required = setting.is_approval_required if setting else True

        if not is_approval_required or user.role == "PM":
            initial_status = "APPROVED"
        else:
            initial_status = "PENDING"

        # 7. 레코드 일괄 생성 및 DB 저장
        for req_date in valid_dates:
            new_leave = models.Leaves(
                user_id=user.user_id,
                date=req_date,
                snapshot_slot_label=snapshot.slot_label,
                snapshot_start_min=snapshot.start_min,
                snapshot_end_min=snapshot.end_min,
                snapshot_deduction_hours=snapshot.deduction_hours,
                status=initial_status,
                year=req_date.year,
                is_deductive=is_deductive,
                reason=reason.strip() if reason else None
            )
            db.add(new_leave)

        # 알림 연동
        if initial_status == "PENDING":
            approvers = db.query(models.Users).filter(
                models.Users.is_active == True,
                (
                    ((models.Users.role == "TEAM_LEAD") & (models.Users.company == user.company) & (models.Users.team == user.team)) |
                    (models.Users.role == "PM")
                )
            ).all()
            
            comma_dates_str = ",".join([d.strftime("%Y-%m-%d") for d in valid_dates])
            msg_content = f"[연차 결재 대기] {user.user_name}님이 {comma_dates_str} 연차 신청에 대해 승인을 대기 중입니다."
            
            for appr in approvers:
                if appr.user_id != user.user_id:
                    utils.create_notification(db, user_id=appr.user_id, sender_id=user.user_id, message=msg_content)

        # 단일 감사 로그 연동
        comma_dates_str = ",".join([d.strftime("%Y-%m-%d") for d in valid_dates])
        audit = models.AuditLogs(
            actor_id=user.user_id,
            action="APPLY_LEAVE_BULK",
            target_info=f"Leaves for {comma_dates_str}",
            old_data="",
            new_data=f"status={initial_status};is_deductive={is_deductive}"
        )
        db.add(audit)

        db.commit()

        msg = "신청되었습니다." if initial_status == "PENDING" else "신청 및 자동 승인되었습니다."
        if is_multiple:
            msg = f"{len(valid_dates)}일의 연차가 " + msg
        return msg

    except LeaveInputValidationError:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        raise RuntimeError(f"서버 오류: {str(e)}")
