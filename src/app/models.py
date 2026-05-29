from sqlalchemy import Column, Integer, String, Boolean, Date, DateTime, ForeignKey, UniqueConstraint, Float, Index
from sqlalchemy.orm import relationship
import datetime
from .database import Base

class Users(Base):
    __tablename__ = "users"

    user_id = Column(String, primary_key=True, index=True) # Redmine ID
    user_name = Column(String, nullable=False)
    company = Column(String)
    team = Column(String)
    password = Column(String, nullable=False)
    total_leave_hours = Column(Integer, default=120) # 15일 * 8시간 = 120시간
    is_active = Column(Boolean, default=True)
    is_admin = Column(Boolean, default=False)  # 레거시 호환 — 새 코드는 role 기반
    role = Column(String, default="STAFF", nullable=False)  # STAFF | TEAM_LEAD | PM | ADMIN
    position = Column(String(60), nullable=True)  # 표시용 직급명 (자유 입력)
    token_version = Column(Integer, default=0, nullable=False)

    leaves = relationship("Leaves", back_populates="user")
    audits = relationship("AuditLogs", back_populates="actor")
    yearly_allocations = relationship("UserYearlyLeaveAllocations", back_populates="user")

class Leaves(Base):
    __tablename__ = "leaves"
    __table_args__ = (
        Index("ix_leaves_user_id_date", "user_id", "date"),
        Index("ix_leaves_year_date", "year", "date"),
        Index("ix_leaves_year_user_id", "year", "user_id"),
        Index("ix_leaves_created_at", "created_at"),
        Index("ix_leaves_status_is_deductive", "status", "is_deductive"),
    )

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(String, ForeignKey("users.user_id"))
    date = Column(Date, nullable=False)
    snapshot_slot_label = Column(String, nullable=False)
    snapshot_start_min = Column(Integer, nullable=False)
    snapshot_end_min = Column(Integer, nullable=False)
    snapshot_deduction_hours = Column(Float, nullable=False)
    status = Column(String, default="APPROVED", nullable=False, index=True)
    rejection_reason = Column(String(500))
    is_deductive = Column(Boolean, default=True, nullable=False) # 연차 차감 여부 (True: 연차, False: 공가/출장 등)
    reason = Column(String(500)) # 신청 사유 (특히 비차감 건의 경우 필수 입력 권장)
    created_at = Column(DateTime, default=datetime.datetime.now)
    year = Column(Integer, nullable=False)

    user = relationship("Users", back_populates="leaves")

class AuditLogs(Base):
    __tablename__ = "audit_logs"
    __table_args__ = (
        Index("ix_audit_logs_actor_id", "actor_id"),
        Index("ix_audit_logs_timestamp", "timestamp"),
        Index("ix_audit_logs_action", "action"),
    )

    id = Column(Integer, primary_key=True, index=True)
    actor_id = Column(String, ForeignKey("users.user_id"))
    action = Column(String, nullable=False) # e.g., UPDATE_USER, DELETE_LEAVE
    target_info = Column(String, nullable=False)
    old_data = Column(String)
    new_data = Column(String)
    timestamp = Column(DateTime, default=datetime.datetime.now)

    actor = relationship("Users", back_populates="audits")

class Holidays(Base):
    __tablename__ = "holidays"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    date = Column(Date, nullable=False, unique=True, index=True)
    created_at = Column(DateTime, default=datetime.datetime.now)


class UserYearlyLeaveAllocations(Base):
    __tablename__ = "user_yearly_leave_allocations"
    __table_args__ = (UniqueConstraint("user_id", "year", name="uq_user_yearly_leave_allocation_user_year"),)

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(String, ForeignKey("users.user_id"), nullable=False, index=True)
    year = Column(Integer, nullable=False, index=True)
    allocated_hours = Column(Integer, nullable=False)
    created_at = Column(DateTime, default=datetime.datetime.now)
    updated_at = Column(DateTime, default=datetime.datetime.now, onupdate=datetime.datetime.now)

    user = relationship("Users", back_populates="yearly_allocations")


class SystemSettings(Base):
    __tablename__ = "system_settings"

    id = Column(Integer, primary_key=True, index=True)
    is_approval_required = Column(Boolean, default=False, nullable=False)
    time_granularity_minutes = Column(Integer, default=60, nullable=False)
    work_start_minute = Column(Integer, default=9 * 60, nullable=False)
    work_end_minute = Column(Integer, default=18 * 60, nullable=False)
    lunch_start_minute = Column(Integer)
    lunch_end_minute = Column(Integer)
    # 화면 브랜딩 (마스터 관리에서 변경)
    product_display_name = Column(String(120), default="쉼(SHIM) 프로젝트 개발 운영", nullable=False)
    # 상단 바·관리자 사이드바 등에 쓰는 짧은 호칭(비우면 공식명과 동일하게 표시)
    product_nav_short = Column(String(80), default="SHIM", nullable=False)
    # 파란 배지 안 텍스트(약칭·기호 등). SQLite 실제 길이 제한은 스키마 마이그레이션과 맞춤.
    brand_initial = Column(String(32), default="S", nullable=False)
    # 팀원 간 팀 캘린더 공유 활성화 (일반 사용자도 같은 팀 휴가 조회 가능)
    team_calendar_visible = Column(Boolean, default=True, nullable=False)
    # 전사 캘린더 공유 활성화 (일반 사용자도 전사 인원 휴가 조회 가능)
    company_calendar_visible = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=datetime.datetime.now)
    updated_at = Column(DateTime, default=datetime.datetime.now, onupdate=datetime.datetime.now)


