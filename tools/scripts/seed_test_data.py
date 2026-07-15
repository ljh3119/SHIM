import os
import sys
import random
import argparse
import hashlib
import holidays
from datetime import date, timedelta, datetime, timezone
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.app import models, auth, database
from src.app.database import SessionLocal, engine

from sqlalchemy import text

def seed_data(reset: bool = False):
    if reset:
        print("[SEED] Resetting database...")
        # 1. 켜져 있는 서버가 파일 핸들을 쥐고 있어도 파일 디스크립터가 깨지지 않도록
        # 물리 파일을 지우지 않고 테이블 구조만 밀고 다시 생성합니다.
        try:
            with engine.connect() as conn:
                conn.execute(text("PRAGMA foreign_keys=OFF;"))
                models.Base.metadata.drop_all(bind=conn)
                conn.execute(text("PRAGMA foreign_keys=ON;"))
                conn.commit()
            print("[SEED] Dropped all tables from database safely (FK disabled)")
        except Exception as e:
            print(f"[SEED WARNING] Failed to drop tables: {e}")
            
        # Re-create all tables based on current models.py
        models.Base.metadata.create_all(bind=engine)
        print("[SEED] Re-created all database tables from metadata")

        # 3. 빈 공간 조각 모음 및 파일 크기 축소
        try:
            with engine.connect() as conn:
                conn.execute(text("VACUUM;"))
                conn.commit()
            print("[SEED] Vacuumed database to release unused space")
        except Exception as e:
            print(f"[SEED WARNING] Failed to vacuum database: {e}")

    db = SessionLocal()
    try:
        print("[SEED] Starting test data seeding...")

        # 1. Ensure Admin exists
        admin = db.query(models.Users).filter(models.Users.user_id == "admin").first()
        if not admin:
            admin = models.Users(
                user_id="admin",
                user_name="시스템관리자",
                password=auth.get_password_hash("0000"),
                role="ADMIN",
                company="SHIM",
                team="HQ"
            )
            db.add(admin)
            db.commit()
            print("[SEED] Created admin user")
        # Ensure we load admin model from DB
        admin = db.query(models.Users).filter(models.Users.user_id == "admin").first()

        # 2. Define Companies and Teams
        companies = ["A-건설", "B-시스템", "C-테크"]
        teams = ["설계팀", "공정관리팀", "현장지원팀", "IT지원팀"]

        # 3. Create PMs
        pms = [
            ("pm_kim", "김총괄", "A-건설"),
            ("pm_lee", "이사업", "B-시스템")
        ]
        for uid, uname, comp in pms:
            if not db.query(models.Users).filter(models.Users.user_id == uid).first():
                user = models.Users(
                    user_id=uid,
                    user_name=uname,
                    company=comp,
                    team="사업관리",
                    password=auth.get_password_hash("0000"),
                    role="PM",
                    total_leave_hours=120
                )
                db.add(user)
                print(f"[SEED] Created PM: {uid}")

        # 4. Create Team Leads
        leads = [
            ("lead_park", "박팀장", "A-건설", "설계팀"),
            ("lead_choi", "최팀장", "A-건설", "공정관리팀"),
            ("lead_jung", "정팀장", "B-시스템", "현장지원팀"),
            ("lead_kang", "강팀장", "C-테크", "IT지원팀")
        ]
        for uid, uname, comp, team in leads:
            if not db.query(models.Users).filter(models.Users.user_id == uid).first():
                user = models.Users(
                    user_id=uid,
                    user_name=uname,
                    company=comp,
                    team=team,
                    password=auth.get_password_hash("0000"),
                    role="TEAM_LEAD",
                    total_leave_hours=120
                )
                db.add(user)
                print(f"[SEED] Created Lead: {uid}")

        # 5. Create Staff
        for i in range(1, 13):
            uid = f"staff_{i:02d}"
            if not db.query(models.Users).filter(models.Users.user_id == uid).first():
                comp = random.choice(companies)
                team = random.choice(teams)
                user = models.Users(
                    user_id=uid,
                    user_name=f"사원_{i:02d}",
                    company=comp,
                    team=team,
                    password=auth.get_password_hash("0000"),
                    role="STAFF",
                    total_leave_hours=120
                )
                db.add(user)
        db.commit()
        print("[SEED] Created staff users")

        # 6. Create Yearly Allocations
        # Gather all possible years for generated leaves (past 15 days to future 15 days)
        today = date.today()
        target_years = {(today - timedelta(days=15)).year, today.year, (today + timedelta(days=15)).year}
        
        all_users = db.query(models.Users).all()
        for u in all_users:
            for yr in target_years:
                exists = db.query(models.UserYearlyLeaveAllocations).filter(
                    models.UserYearlyLeaveAllocations.user_id == u.user_id,
                    models.UserYearlyLeaveAllocations.year == yr
                ).first()
                if not exists:
                    db.add(models.UserYearlyLeaveAllocations(
                        user_id=u.user_id,
                        year=yr,
                        allocated_hours=120
                    ))
        db.commit()
        print(f"[SEED] Created yearly allocations for years: {list(target_years)}")

        # 6-2. Seed Korean Holidays for target years (Aligned with src/app/main.py seed_korean_holidays)
        def compact_kr_holiday_name(name: str) -> str:
            compact_map = {
                "설날 연휴": "설 연휴",
                "추석 연휴": "추석 연휴",
            }
            normalized = str(name).strip()
            return compact_map.get(normalized, normalized)

        for year in target_years:
            action_name = f"SEED_KR_HOLIDAYS_{year}"
            exists_audit = db.query(models.AuditLogs).filter(models.AuditLogs.action == action_name).first()
            if not exists_audit:
                kr_holidays = holidays.country_holidays("KR", years=[year], language="ko")
                for holiday_date, holiday_name in kr_holidays.items():
                    normalized_name = compact_kr_holiday_name(holiday_name)
                    exists_holiday = db.query(models.Holidays).filter(models.Holidays.date == holiday_date).first()
                    if not exists_holiday:
                        db.add(models.Holidays(name=normalized_name, date=holiday_date))
                
                labor_day = date(year, 5, 1)
                if not db.query(models.Holidays).filter(models.Holidays.date == labor_day).first():
                    db.add(models.Holidays(name="노동절", date=labor_day))

                db.add(
                    models.AuditLogs(
                        actor_id="admin",
                        actor=admin,
                        action=action_name,
                        target_info=f"HolidaySeed:{year}",
                        old_data="None",
                        new_data="KR holiday seed incl. May 1 Labor Day",
                        timestamp=datetime.now(timezone.utc)
                    )
                )
        db.commit()
        print(f"[SEED] Created holidays for years: {list(target_years)}")

        # Fetch all holidays in range to avoid N+1 queries during leave generation
        holiday_dates = {
            h.date for h in db.query(models.Holidays).filter(
                models.Holidays.date >= today - timedelta(days=16),
                models.Holidays.date <= today + timedelta(days=16)
            ).all()
        }

        # 7. Create Leave Requests
        statuses = ["APPROVED", "PENDING", "REJECTED", "CANCELED"]
        
        # 다양한 연차 종류 정의: (label, start_min, end_min, deduction_hours, default_reason)
        leave_options = [
            ("09:00~18:00", 540, 1080, 8.0, "개인 사유 연차"), # 전일
            ("09:00~13:00", 540, 780, 4.0, "오전 개인 반차"), # 오전 반차
            ("14:00~18:00", 840, 1080, 4.0, "오후 개인 반차"), # 오후 반차
            ("09:00~11:00", 540, 660, 2.0, "오전 병원 내원(반반차)"), # 오전 반반차
            ("16:00~18:00", 960, 1080, 2.0, "조기 퇴근(반반차)"), # 오후 반반차
            ("14:00~15:00", 840, 900, 1.0, "개인 용무 외출(시간차)"), # 1시간
        ]

        def get_random_leave_data():
            opt = random.choice(leave_options)
            is_deduct = random.random() > 0.20  # 20% 확률로 공가/출장(비차감)
            if not is_deduct:
                # 사용시간대(label)에는 순수 시간 범위만 들어가도록 수정하고, [공가]/[출장] 접두사는 사유(reason)의 앞단에 주입합니다.
                prefix = random.choice(["[공가] ", "[출장] "])
                label = opt[0]
                reason = prefix + random.choice(["예비군 훈련 참석", "직무 교육 외부 세미나", "고객사 파견 미팅", "정기 건강 검진"])
            else:
                label = opt[0]
                reason = opt[4]
            
            return {
                "label": label,
                "start": opt[1],
                "end": opt[2],
                "hours": opt[3],
                "is_deductive": is_deduct,
                "reason": reason
            }

        # Track remaining leave hours per user and year to avoid exceeding 120 hours limit
        user_remaining_hours = {}
        for u in all_users:
            user_remaining_hours[u.user_id] = {yr: 120.0 for yr in target_years}

        # Get all working days in range [-14, 14] excluding weekends and holidays
        working_days = []
        for d in range(-14, 15):
            leave_date = today + timedelta(days=d)
            if leave_date.weekday() >= 5:
                continue
            if leave_date in holiday_dates:
                continue
            working_days.append(leave_date)
        working_days.sort()

        def get_leave_data_for_opt(opt, is_deduct):
            if not is_deduct:
                prefix = random.choice(["[공가] ", "[출장] "])
                label = opt[0]
                reason = prefix + random.choice(["예비군 훈련 참석", "직무 교육 외부 세미나", "고객사 파견 미팅", "정기 건강 검진"])
            else:
                label = opt[0]
                reason = opt[4]
            return {
                "label": label,
                "start": opt[1],
                "end": opt[2],
                "hours": opt[3],
                "is_deductive": is_deduct,
                "reason": reason
            }

        # Select 1-2 random users to have 5 consecutive days of leave
        # PM, Lead, or Staff
        candidates = [u for u in all_users if u.role != "ADMIN"]
        heavy_user = random.choice(candidates) if candidates else None
        
        if heavy_user and len(working_days) >= 5:
            # Find 5 consecutive working days
            start_idx = random.randint(0, len(working_days) - 5)
            consecutive_days = working_days[start_idx : start_idx + 5]
            for leave_date in consecutive_days:
                req_year = leave_date.year
                
                # Full day leave
                ldata = {
                    "label": "09:00~18:00",
                    "start": 540,
                    "end": 1080,
                    "hours": 8.0,
                    "is_deductive": True,
                    "reason": "정기 리프레시 휴가 (5일 연속)"
                }
                
                # Check limit
                rem = user_remaining_hours[heavy_user.user_id].get(req_year, 120.0)
                if rem >= 8.0:
                    user_remaining_hours[heavy_user.user_id][req_year] -= 8.0
                    db.add(models.Leaves(
                        user_id=heavy_user.user_id,
                        date=leave_date,
                        snapshot_slot_label=ldata["label"],
                        snapshot_start_min=ldata["start"],
                        snapshot_end_min=ldata["end"],
                        snapshot_deduction_hours=ldata["hours"],
                        status="APPROVED", # Always approved for 5 consecutive days (annual leave)
                        is_deductive=ldata["is_deductive"],
                        reason=ldata["reason"],
                        year=req_year
                    ))

        # Generate some leaves for other users
        for u in all_users:
            if u.role == "ADMIN":
                continue
            if heavy_user and u.user_id == heavy_user.user_id:
                # Heavy user already has their 5-day block, don't generate more leaves for them
                continue
                
            # Assign a random target monthly limit for active leaves (8h to 16h on average, some less)
            monthly_limit = random.choices([0.0, 4.0, 8.0, 12.0, 16.0], weights=[10, 15, 30, 25, 20])[0]
            user_seeded_hours = 0.0
            non_deductive_count = 0
            
            # Shuffle the working days to randomize when leaves occur
            user_days = list(working_days)
            random.shuffle(user_days)
            
            for leave_date in user_days:
                req_year = leave_date.year
                is_past = leave_date < today
                
                # 1. Option for non-deductive leave (공가/출장) - independent of monthly limit
                if non_deductive_count < 1 and random.random() < 0.04:
                    # Determine status
                    if is_past:
                        status = random.choices(["APPROVED", "REJECTED", "CANCELED"], weights=[80, 10, 10])[0]
                    else:
                        status = "APPROVED" if u.role == "PM" else random.choices(["PENDING", "APPROVED"], weights=[80, 20])[0]
                    
                    opt = random.choice(leave_options)
                    ldata = get_leave_data_for_opt(opt, is_deduct=False)
                    
                    db.add(models.Leaves(
                        user_id=u.user_id,
                        date=leave_date,
                        snapshot_slot_label=ldata["label"],
                        snapshot_start_min=ldata["start"],
                        snapshot_end_min=ldata["end"],
                        snapshot_deduction_hours=ldata["hours"],
                        status=status,
                        rejection_reason="업무 과다로 인한 반려" if status == "REJECTED" else "",
                        is_deductive=ldata["is_deductive"],
                        reason=ldata["reason"],
                        year=req_year
                    ))
                    non_deductive_count += 1
                    continue # Only one leave per day
                
                # 2. Option for deductive leave (연차 등) - limited by monthly_limit
                if user_seeded_hours < monthly_limit and random.random() < 0.25:
                    # Filter options that fit within remaining limit
                    remaining = monthly_limit - user_seeded_hours
                    valid_opts = [o for o in leave_options if o[3] <= remaining]
                    if not valid_opts:
                        continue
                        
                    opt = random.choice(valid_opts)
                    
                    # Determine status
                    if is_past:
                        status = random.choices(["APPROVED", "REJECTED", "CANCELED"], weights=[80, 10, 10])[0]
                    else:
                        status = "APPROVED" if u.role == "PM" else random.choices(["PENDING", "APPROVED"], weights=[80, 20])[0]
                    
                    ldata = get_leave_data_for_opt(opt, is_deduct=True)
                    
                    # If status is APPROVED or PENDING, it counts towards limit
                    if status in ["APPROVED", "PENDING"]:
                        # Check database/user limits
                        rem = user_remaining_hours[u.user_id].get(req_year, 120.0)
                        if rem < ldata["hours"]:
                            continue
                        user_remaining_hours[u.user_id][req_year] -= ldata["hours"]
                        user_seeded_hours += ldata["hours"]
                        
                    db.add(models.Leaves(
                        user_id=u.user_id,
                        date=leave_date,
                        snapshot_slot_label=ldata["label"],
                        snapshot_start_min=ldata["start"],
                        snapshot_end_min=ldata["end"],
                        snapshot_deduction_hours=ldata["hours"],
                        status=status,
                        rejection_reason="업무 과다로 인한 반려" if status == "REJECTED" else "",
                        is_deductive=ldata["is_deductive"],
                        reason=ldata["reason"],
                        year=req_year
                    ))
        
        db.commit()
        print("[SEED] Created leave requests")

        # 8. Create Audit Logs
        actions = [
            ("USER_UPDATE", "사원 정보 수정"),
            ("USER_CREATE", "사원 생성"),
            ("SYSTEM_SETTING_UPDATE", "시스템 설정 변경"),
            ("LEAVE_DELETE", "연차 기록 삭제"),
            ("LEAVE_STATUS_CHANGE", "결재 상태 변경")
        ]
        
        for _ in range(20):
            action_code, action_kr = random.choice(actions)
            target_user = random.choice(all_users)
            db.add(models.AuditLogs(
                actor_id="admin",
                actor=admin,  # Pass the admin object explicitly to ensure actor_name/actor_department are snapshotted by listener
                action=action_code,
                target_info=f"Target: {target_user.user_id}",
                old_data="{}",
                new_data="{\"note\": \"Seed data\"}",
                timestamp=datetime.now(timezone.utc) - timedelta(days=random.randint(0, 10))
            ))
        db.commit()
        print("[SEED] Created audit logs with actor snapshots")

        # 9. Ensure System Settings exists and sync key_hash_snapshot
        current_key = auth.get_encryption_key()
        current_key_hash = hashlib.sha256(current_key).hexdigest() if current_key else "PLAINTEXT_MODE"
        
        settings = db.query(models.SystemSettings).first()
        if not settings:
            settings = models.SystemSettings(
                is_approval_required=False,
                time_granularity_minutes=60,
                work_start_minute=9 * 60,
                work_end_minute=18 * 60,
                lunch_start_minute=12 * 60,
                lunch_end_minute=13 * 60,
                product_display_name="쉼(SHIM) 프로젝트 개발 운영",
                product_nav_short="",
                brand_initial="S",
                team_calendar_visible=True,
                company_calendar_visible=False,
                key_hash_snapshot=current_key_hash
            )
            db.add(settings)
            print("[SEED] Created default system settings with key_hash_snapshot")
        else:
            settings.key_hash_snapshot = current_key_hash
            print("[SEED] Synchronized key_hash_snapshot in system settings")
        
        db.commit()
        print("[SEED] Test data seeding completed successfully!")

    except Exception as e:
        db.rollback()
        print(f"[SEED] Error: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="SHIM test data seeding script")
    parser.add_argument("--reset", "-r", action="store_true", help="Reset database before seeding")
    args = parser.parse_args()
    
    seed_data(reset=args.reset)
