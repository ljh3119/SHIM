from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from .. import models

from types import SimpleNamespace

LEAVE_STATUSES = frozenset({"PENDING", "APPROVED", "REJECTED", "CANCELED"})
ALLOWED_LEAVE_STATUS_TRANSITIONS = frozenset(
    {
        ("PENDING", "APPROVED"),
        ("PENDING", "REJECTED"),
        ("PENDING", "CANCELED"),
        ("APPROVED", "CANCELED"),
    }
)
REJECTION_REASON_MAX_LENGTH = 500
ALLOWED_TIME_GRANULARITIES = frozenset({30, 60, 120})

_SYSTEM_SETTINGS_CACHE = None

def get_system_settings(db: Session, force_reload: bool = False) -> SimpleNamespace | None:
    global _SYSTEM_SETTINGS_CACHE
    if _SYSTEM_SETTINGS_CACHE is not None and not force_reload:
        return _SYSTEM_SETTINGS_CACHE

    setting = db.query(models.SystemSettings).first()
    if not setting:
        return None
    _SYSTEM_SETTINGS_CACHE = SimpleNamespace(
        id=setting.id,
        is_approval_required=setting.is_approval_required,
        time_granularity_minutes=setting.time_granularity_minutes,
        work_start_minute=setting.work_start_minute,
        work_end_minute=setting.work_end_minute,
        lunch_start_minute=setting.lunch_start_minute,
        lunch_end_minute=setting.lunch_end_minute,
        product_display_name=setting.product_display_name,
        product_nav_short=setting.product_nav_short,
        brand_initial=setting.brand_initial,
        team_calendar_visible=setting.team_calendar_visible,
        company_calendar_visible=setting.company_calendar_visible,
    )
    return _SYSTEM_SETTINGS_CACHE



@dataclass
class SnapshotPayload:
    slot_label: str
    start_min: int
    end_min: int
    deduction_hours: float


@dataclass
class LeaveStatusTransitionResult:
    old_status: str
    new_status: str
    old_rejection_reason: str
    new_rejection_reason: str

    @property
    def audit_old_data(self) -> str:
        reason_state = "SET" if self.old_rejection_reason else "NONE"
        return f"status={self.old_status};rejection_reason={reason_state}"

    @property
    def audit_new_data(self) -> str:
        reason_state = "SET" if self.new_rejection_reason else "NONE"
        return f"status={self.new_status};rejection_reason={reason_state}"


class LeaveStatusTransitionError(ValueError):
    pass


class LeaveInputValidationError(ValueError):
    pass


def resolve_time_policy_setting(db: Session) -> tuple[int, int | None, int | None, int, int]:
    setting = get_system_settings(db)
    if not setting:
        return 60, None, None, 9 * 60, 18 * 60
    granularity = int(getattr(setting, "time_granularity_minutes", 60) or 60)
    lunch_start = getattr(setting, "lunch_start_minute", None)
    lunch_end = getattr(setting, "lunch_end_minute", None)
    work_start = int(getattr(setting, "work_start_minute", 9 * 60) or (9 * 60))
    work_end = int(getattr(setting, "work_end_minute", 18 * 60) or (18 * 60))
    if granularity not in ALLOWED_TIME_GRANULARITIES:
        granularity = 60
    if work_start < 0 or work_start > 1439:
        work_start = 9 * 60
    if work_end < 1 or work_end > 1440:
        work_end = 18 * 60
    if work_end <= work_start:
        work_start = 9 * 60
        work_end = 18 * 60
    return granularity, lunch_start, lunch_end, work_start, work_end


def _parse_hhmm_to_minutes(value: str, field_name: str) -> int:
    text = (value or "").strip()
    try:
        hh_str, mm_str = text.split(":")
        hh = int(hh_str)
        mm = int(mm_str)
    except (ValueError, AttributeError):
        raise LeaveInputValidationError(f"{field_name} 형식이 올바르지 않습니다. HH:MM 형식으로 입력해 주세요.")
    if hh < 0 or hh > 23 or mm < 0 or mm > 59:
        raise LeaveInputValidationError(f"{field_name} 값이 올바르지 않습니다.")
    return hh * 60 + mm


def _format_minutes_to_hhmm(value: int) -> str:
    hh = value // 60
    mm = value % 60
    return f"{hh:02d}:{mm:02d}"


def _overlap_minutes(start_a: int, end_a: int, start_b: int, end_b: int) -> int:
    return max(0, min(end_a, end_b) - max(start_a, start_b))


def build_snapshot_from_timerange(
    start_time: str,
    end_time: str,
    granularity_minutes: int,
    lunch_start_minute: int | None,
    lunch_end_minute: int | None,
    work_start_minute: int,
    work_end_minute: int,
) -> SnapshotPayload:
    if granularity_minutes not in ALLOWED_TIME_GRANULARITIES:
        raise LeaveInputValidationError("지원하지 않는 시간 단위 정책입니다.")

    start_min = _parse_hhmm_to_minutes(start_time, "시작 시간")
    end_min = _parse_hhmm_to_minutes(end_time, "종료 시간")
    if end_min <= start_min:
        raise LeaveInputValidationError("종료 시간은 시작 시간보다 늦어야 합니다.")
    start_on_boundary = (start_min - work_start_minute) % granularity_minutes == 0
    end_on_boundary = (end_min - work_start_minute) % granularity_minutes == 0
    # 업무 종료 시각은 단위 경계와 정확히 맞지 않아도 선택 가능해야 하루 전체 신청이 가능하다.
    end_on_allowed_edge = end_min == work_end_minute
    if not start_on_boundary or (not end_on_boundary and not end_on_allowed_edge):
        raise LeaveInputValidationError("입력 시각은 설정된 시간 단위 경계에 맞아야 합니다.")
    if start_min < work_start_minute or end_min > work_end_minute:
        raise LeaveInputValidationError("업무시간 범위를 벗어난 시간은 신청할 수 없습니다.")

    total_minutes = end_min - start_min
    if total_minutes < granularity_minutes:
        raise LeaveInputValidationError("선택 구간이 설정된 최소 시간 단위보다 짧습니다.")
    excluded_lunch_minutes = 0
    if lunch_start_minute is not None and lunch_end_minute is not None and lunch_end_minute > lunch_start_minute:
        excluded_lunch_minutes = _overlap_minutes(start_min, end_min, lunch_start_minute, lunch_end_minute)

    effective_minutes = total_minutes - excluded_lunch_minutes
    if effective_minutes <= 0:
        raise LeaveInputValidationError("점심시간 제외 후 차감 시간이 0 이하입니다. 시간을 다시 선택해 주세요.")
    deduction_hours = effective_minutes / 60.0
    label = f"{_format_minutes_to_hhmm(start_min)}~{_format_minutes_to_hhmm(end_min)}"
    return SnapshotPayload(slot_label=label, start_min=start_min, end_min=end_min, deduction_hours=deduction_hours)


def get_default_leave_status(db: Session) -> str:
    setting = get_system_settings(db)
    if setting and setting.is_approval_required:
        return "PENDING"
    return "APPROVED"


def normalize_leave_status(status_value: str) -> str:
    normalized = (status_value or "").strip().upper()
    if normalized not in LEAVE_STATUSES:
        raise LeaveStatusTransitionError("지원하지 않는 상태값입니다.")
    return normalized


def normalize_rejection_reason(reason: str | None) -> str:
    normalized = (reason or "").strip()
    if not normalized:
        raise LeaveStatusTransitionError("반려 처리 시 반려 사유를 입력해 주세요.")
    if len(normalized) > REJECTION_REASON_MAX_LENGTH:
        raise LeaveStatusTransitionError(f"반려 사유는 최대 {REJECTION_REASON_MAX_LENGTH}자까지 입력할 수 있습니다.")
    return normalized


def apply_leave_status_transition(
    leave: models.Leaves,
    status_value: str,
    rejection_reason: str | None = None,
) -> LeaveStatusTransitionResult:
    old_status = normalize_leave_status(leave.status or "APPROVED")
    new_status = normalize_leave_status(status_value)
    old_reason = (getattr(leave, "rejection_reason", None) or "").strip()

    if old_status != new_status and (old_status, new_status) not in ALLOWED_LEAVE_STATUS_TRANSITIONS:
        raise LeaveStatusTransitionError(f"{old_status} 상태에서 {new_status} 상태로 변경할 수 없습니다.")

    new_reason = normalize_rejection_reason(rejection_reason) if new_status == "REJECTED" else ""

    leave.status = new_status
    leave.rejection_reason = new_reason

    return LeaveStatusTransitionResult(
        old_status=old_status,
        new_status=new_status,
        old_rejection_reason=old_reason,
        new_rejection_reason=new_reason,
    )
