import sys
import os
from pathlib import Path

# Add src to path
sys.path.append(str(Path(__file__).resolve().parents[2] / "src"))

from app import models, database, auth
from app.database import engine, SessionLocal
import datetime

def test_deletion_flow():
    db = SessionLocal()
    try:
        # 1. Create a dummy user if not exists
        user = db.query(models.Users).filter(models.Users.user_id == "test_del_user").first()
        if not user:
            user = models.Users(
                user_id="test_del_user",
                user_name="삭제테스트",
                password="hash",
                role="STAFF",
                is_active=True
            )
            db.add(user)
            db.commit()
            db.refresh(user)

        # 2. Create a dummy leave
        leave = models.Leaves(
            user_id=user.user_id,
            date=datetime.date.today(),
            snapshot_slot_label="09:00 - 10:00",
            snapshot_start_min=540,
            snapshot_end_min=600,
            snapshot_deduction_hours=1.0,
            status="APPROVED",
            year=datetime.date.today().year
        )
        db.add(leave)
        db.commit()
        db.refresh(leave)
        leave_id = leave.id
        print(f"[TEST] Created leave ID: {leave_id}")

        # 3. Simulate deletion logic from api_admin.py
        target_leave = db.query(models.Leaves).filter(models.Leaves.id == leave_id).first()
        if not target_leave:
            print("[ERROR] Leave not found after creation")
            return

        # Pre-fetch info for audit log
        leave_user_name = target_leave.user.user_name
        leave_date = target_leave.date
        leave_status = target_leave.status
        leave_hours = target_leave.snapshot_deduction_hours

        print(f"[TEST] Deleting leave for {leave_user_name} on {leave_date}")

        # Audit log creation
        audit = models.AuditLogs(
            actor_id="admin",
            action="DELETE_LEAVE",
            target_info=f"Leave:{leave_id} ({leave_user_name}, {leave_date})",
            old_data=f"Status:{leave_status}, Date:{leave_date}, Hours:{leave_hours}",
            new_data="DELETED"
        )
        db.add(audit)
        
        # Actual deletion
        db.delete(target_leave)
        db.commit()
        print("[TEST] Deletion and Commit successful")

        # 4. Verify
        deleted_leave = db.query(models.Leaves).filter(models.Leaves.id == leave_id).first()
        if deleted_leave:
            print("[FAILURE] Leave still exists in DB")
        else:
            print("[SUCCESS] Leave successfully removed from DB")

    except Exception as e:
        db.rollback()
        print(f"[ERROR] Exception occurred: {str(e)}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()

if __name__ == "__main__":
    test_deletion_flow()
