import os
import sys
import random
from datetime import date, timedelta, datetime
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.app import models, auth, database
from src.app.database import SessionLocal

def seed_data():
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
                is_admin=True,
                role="ADMIN",
                company="SHIM",
                team="HQ"
            )
            db.add(admin)
            db.commit()
            print("[SEED] Created admin user")

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
        current_year = date.today().year
        all_users = db.query(models.Users).all()
        for u in all_users:
            exists = db.query(models.UserYearlyLeaveAllocations).filter(
                models.UserYearlyLeaveAllocations.user_id == u.user_id,
                models.UserYearlyLeaveAllocations.year == current_year
            ).first()
            if not exists:
                db.add(models.UserYearlyLeaveAllocations(
                    user_id=u.user_id,
                    year=current_year,
                    allocated_hours=120
                ))
        db.commit()
        print("[SEED] Created yearly allocations")

        # 7. Create Leave Requests
        statuses = ["APPROVED", "PENDING", "REJECTED", "CANCELED"]
        today = date.today()
        
        # Generate some past leaves (mostly approved)
        for u in all_users:
            if u.role == "ADMIN": continue
            # Past 30 days
            for d in range(1, 15):
                if random.random() > 0.7:
                    leave_date = today - timedelta(days=d)
                    if leave_date.weekday() >= 5: continue # Skip weekends
                    
                    status = random.choices(statuses, weights=[70, 0, 20, 10])[0]
                    reason = "개인 사유" if status == "REJECTED" else ""
                    
                    db.add(models.Leaves(
                        user_id=u.user_id,
                        date=leave_date,
                        snapshot_slot_label="09:00~18:00",
                        snapshot_start_min=540,
                        snapshot_end_min=1080,
                        snapshot_deduction_hours=8.0,
                        status=status,
                        rejection_reason=reason,
                        year=leave_date.year
                    ))

        # Generate some future leaves (mostly pending)
        for u in all_users:
            if u.role == "ADMIN": continue
            # Future 30 days
            for d in range(1, 15):
                if random.random() > 0.8:
                    leave_date = today + timedelta(days=d)
                    if leave_date.weekday() >= 5: continue
                    
                    status = random.choices(["PENDING", "APPROVED"], weights=[80, 20])[0]
                    # PM leaves are auto-approved
                    if u.role == "PM": status = "APPROVED"
                    
                    db.add(models.Leaves(
                        user_id=u.user_id,
                        date=leave_date,
                        snapshot_slot_label="09:00~18:00",
                        snapshot_start_min=540,
                        snapshot_end_min=1080,
                        snapshot_deduction_hours=8.0,
                        status=status,
                        year=leave_date.year
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
            db.add(models.AuditLogs(
                actor_id="admin",
                action=action_code,
                target_info=f"Target: {random.choice(all_users).user_id}",
                old_data="{}",
                new_data="{\"note\": \"Seed data\"}",
                timestamp=datetime.now() - timedelta(days=random.randint(0, 10))
            ))
        db.commit()
        print("[SEED] Created audit logs")

        print("[SEED] Test data seeding completed successfully!")

    except Exception as e:
        db.rollback()
        print(f"[SEED] Error: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    seed_data()
