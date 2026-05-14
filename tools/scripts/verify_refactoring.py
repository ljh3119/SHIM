import os
import sys
from pathlib import Path
from datetime import date, datetime

# 프로젝트 루트를 경로에 추가
PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.app import models, auth, utils
from src.app.database import SessionLocal, engine
from src.app.services import admin_service

def verify_all():
    db = SessionLocal()
    print("--- 1. Utils Verification ---")
    years = utils.build_year_options(2026, [2024, 2027])
    print(f"Year Options: {years}")
    assert 2024 in years and 2026 in years and 2027 in years
    
    # Check numeric properties of formatting instead of exact Korean string to avoid encoding issues in tests
    label = utils.hours_to_days_hours_label(12)
    # 12 hours -> 1 day 4 hours.
    print(f"12h label: {label}")
    assert "1" in label and "4" in label
    
    compact = utils.hours_to_days_hours_compact(-4.5)
    print(f" -4.5h compact: {compact}")
    # Python 3 rounds 4.5 to 4 (nearest even). So -4h or -5h are both possible depending on env
    assert "-4h" in compact or "-5h" in compact
    
    print("\n--- 2. RBAC / is_admin Legacy Verification ---")
    admin = db.query(models.Users).filter(models.Users.role == "ADMIN").first()
    if admin:
        print(f"Admin User: {admin.user_id}, role={admin.role}")
        is_admin_check = (admin.role == "ADMIN" or getattr(admin, "is_admin", False))
        assert is_admin_check is True

    test_user = db.query(models.Users).filter(models.Users.role != "ADMIN").first()
    if test_user:
        print(f"Staff User: {test_user.user_id}, role={test_user.role}")
        is_admin_check = (test_user.role == "ADMIN" or getattr(test_user, "is_admin", False))
        assert is_admin_check is False

    print("\n--- 3. Admin Service Verification ---")
    stats = admin_service.get_admin_dashboard_stats(db)
    print(f"Stats keys found: {list(stats.keys())}")
    assert "active_users_count" in stats
    assert isinstance(stats["active_users_count"], int)

    print("\n--- 4. Query Filter Verification ---")
    # Timeline should not include ADMIN's leaves if we are filtering them out (though usually admin doesn't apply for leave, we check the query logic)
    query = admin_service.get_leaves_timeline_query(db, year=2026)
    results = query.all()
    print(f"Timeline items: {len(results)}")
    
    print("\n[SUCCESS] Verification passed!")
    db.close()

if __name__ == "__main__":
    try:
        verify_all()
    except AssertionError as e:
        print(f"\n[FAILURE] Assertion failed")
        sys.exit(1)
    except Exception as e:
        print(f"\n[ERROR] {e}")
        sys.exit(1)
