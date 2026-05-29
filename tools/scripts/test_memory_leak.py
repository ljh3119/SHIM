import os
import sys
import gc
import time
import tracemalloc
import asyncio
try:
    import psutil
except ImportError:
    print("[ERROR] 'psutil' package is required to run this memory leak test.")
    print("Please install development dependencies using: pip install -r requirements-dev.txt")
    sys.exit(1)

from httpx import AsyncClient

# 프로젝트 루트 경로를 Python path에 추가하여 src 패키지 로드 보장
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# 환경 변수 설정 (테스트용 DB 생성 및 KST 타임존 지정)
os.environ["SHIM_PORT"] = "8000"
os.environ["SHIM_SECRET_KEY"] = "shim_test_secret_key_memory_leak_verification_12345"
os.environ["SHIM_DATA_DIR"] = os.path.abspath(os.path.join(project_root, "var/data_test"))

# DB 및 모델 로드
from src.app.database import SessionLocal, engine, Base
from src.app.main import app
from src.app.models import Users, Leaves, AuditLogs
from src.app.auth import get_password_hash

# 헬퍼 함수: DB 강제 초기화
def init_test_db():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    
    # 기본 테스트 계정 생성 (ADMIN, PM, STAFF)
    db = SessionLocal()
    try:
        admin = Users(
            user_id="admin",
            password=get_password_hash("admin123"),
            user_name="관리자",
            role="ADMIN",
            position="대표",
            company="본사",
            team="관리팀",
            total_leave_hours=120,
            is_active=True
        )
        pm = Users(
            user_id="pm",
            password=get_password_hash("pm123"),
            user_name="PM사원",
            role="PM",
            position="수석",
            company="본사",
            team="개발팀",
            total_leave_hours=120,
            is_active=True
        )
        staff = Users(
            user_id="staff",
            password=get_password_hash("staff123"),
            user_name="일반사원",
            role="STAFF",
            position="선임",
            company="본사",
            team="개발팀",
            total_leave_hours=120,
            is_active=True
        )
        db.add_all([admin, pm, staff])
        
        # 연도별 할당 데이터 추가
        from src.app.models import UserYearlyLeaveAllocations
        for year in [2026, 2027]:
            db.add_all([
                UserYearlyLeaveAllocations(user_id="admin", year=year, allocated_hours=120),
                UserYearlyLeaveAllocations(user_id="pm", year=year, allocated_hours=120),
                UserYearlyLeaveAllocations(user_id="staff", year=year, allocated_hours=120)
            ])
            
        db.commit()
    except Exception as e:
        print(f"[DB INIT ERROR] Seeding failed: {e}")
        db.rollback()
        raise e
    finally:
        db.close()

async def run_stability_and_memory_leak_test_async(iterations=1000):
    print("=" * 60)
    print("SHIM Long-Running System Stability & Memory Leak Verification (Async)")
    print(f"Target Iterations: {iterations}")
    print("=" * 60)
    
    # 1. DB 초기화
    init_test_db()
    
    # 2. tracemalloc 기동
    tracemalloc.start()
    process = psutil.Process(os.getpid())
    
    init_rss = process.memory_info().rss
    print(f"[STAGE 0] Initial Memory RSS: {init_rss / 1024 / 1024:.2f} MB")
    snapshot_start = tracemalloc.take_snapshot()
    
    start_time = time.time()
    
    # 3. 비동기 클라이언트 구동
    async with AsyncClient(app=app, base_url="http://test") as client:
        # 로그인 및 쿠키 획득 (STAFF 권한)
        response = await client.post("/login", data={"user_id": "staff", "password": "staff123"}, follow_redirects=False)
        if response.status_code != 302:
            print(f"[ERROR] Login failed! Status: {response.status_code}")
            return False
            
        print(f"\n[STAGE 1] Running {iterations} API request cycles...")
        for i in range(1, iterations + 1):
            # 1) 개인 대시보드 조회
            await client.get("/")
            
            # 2) 팀원 캘린더 조회
            await client.get("/user/team/calendar")
            
            # 3) 연차 신청
            day_offset = (i % 20) + 1
            date_str = f"2026-06-{day_offset:02d}"
            if day_offset in [6, 7, 13, 14, 20, 21]:
                date_str = "2026-06-01"
                
            await client.post("/user/leave", data={
                "leave_date": date_str,
                "start_time": "",
                "end_time": "",
                "is_deductive": "true",
                "reason": f"정기 가동 안정성 테스트 신청 {i}"
            })
            
            # 100회마다 주기적 메모리 계측
            if i % 100 == 0:
                current_rss = process.memory_info().rss
                elapsed = time.time() - start_time
                rate = i / elapsed
                print(f"  - Request {i}/{iterations} done. Memory RSS: {current_rss / 1024 / 1024:.2f} MB ({rate:.1f} req/sec)")

    # 4. 시나리오 C: 대량 데이터 적재 및 엑셀 다운로드 피크 메모리 테스트
    print("\n[STAGE 2] Seeding 1,500 fake audit logs for export test...")
    db = SessionLocal()
    try:
        fake_logs = []
        for k in range(1500):
            fake_logs.append(AuditLogs(
                actor_id="staff",
                action="APPLY_LEAVE",
                target_info=f"Leave date: 2026-06-01 (1.0 days), Loop={k}",
                old_data="{}",
                new_data="{}"
            ))
        db.bulk_save_objects(fake_logs)
        db.commit()
    finally:
        db.close()
        
    print("[STAGE 2] Simulating Admin Audit Export (Excel) multi-calls...")
    
    async with AsyncClient(app=app, base_url="http://test") as admin_client:
        # ADMIN 계정으로 로그인 수행
        response = await admin_client.post("/login", data={"user_id": "admin", "password": "admin123"}, follow_redirects=False)
        if response.status_code != 302:
            print(f"[ERROR] Admin login failed! Status: {response.status_code}")
            return False
            
        pre_export_rss = process.memory_info().rss
        print(f"  - Pre-Export RSS: {pre_export_rss / 1024 / 1024:.2f} MB")
        
        # 엑셀 다운로드 API 5회 연속 호출
        for m in range(5):
            resp = await admin_client.get("/admin/audit/export")
            if resp.status_code == 200:
                _ = resp.content
                
        post_export_rss = process.memory_info().rss
        print(f"  - Post-Export RSS: {post_export_rss / 1024 / 1024:.2f} MB")
        
    # 5. 강제 GC 수행 및 회귀 측정
    print("\n[STAGE 3] Collecting garbage and evaluating memory leak...")
    
    # 의도적으로 로컬 변수 참조 제거
    if 'client' in locals(): del client
    if 'response' in locals(): del response
    if 'admin_client' in locals(): del admin_client
    if 'resp' in locals(): del resp
    if 'fake_logs' in locals(): del fake_logs
    if 'db' in locals(): del db
    
    await asyncio.sleep(2)
    gc.collect()
    gc.collect()
    
    final_rss = process.memory_info().rss
    snapshot_end = tracemalloc.take_snapshot()
    
    # 6. 결과 분석 보고
    elapsed_total = time.time() - start_time
    print("\n" + "=" * 60)
    print("STABILITY & MEMORY LEAK REPORT (ASYNC)")
    print("=" * 60)
    print(f"Total Elapsed Time: {elapsed_total:.2f} seconds")
    print(f"Initial Memory RSS: {init_rss / 1024 / 1024:.2f} MB")
    print(f"Peak Export Memory: {post_export_rss / 1024 / 1024:.2f} MB")
    print(f"Final Memory RSS  : {final_rss / 1024 / 1024:.2f} MB")
    
    diff_rss = final_rss - init_rss
    print(f"Net Memory Increase (RSS): {diff_rss / 1024 / 1024:.2f} MB")
    
    stats = snapshot_end.compare_to(snapshot_start, 'lineno')
    total_heap_diff = sum(stat.size_diff for stat in stats)
    total_heap_diff_mb = total_heap_diff / 1024 / 1024
    print(f"Net Heap Memory Increase (tracemalloc): {total_heap_diff_mb:.2f} MB ({total_heap_diff} bytes)")
    
    print("\n[Top 5 Memory Allocation Diffs]")
    for stat in stats[:5]:
        print(stat)
        
    print("=" * 60)
    
    # 누출 판정
    heap_passed = total_heap_diff_mb < 1.0
    rss_passed = (diff_rss / 1024 / 1024) < 30.0
    
    if heap_passed and rss_passed:
        print("[SUCCESS] Memory leak test PASSED. System returns to clean state.")
        return True
    else:
        if not heap_passed:
            print("[WARNING] Significant Python heap memory growth detected (> 1.0 MB).")
        if not rss_passed:
            print("[WARNING] Significant physical memory (RSS) growth detected (> 30.0 MB).")
        print("[WARNING] Review database/session cleanup.")
        return False

if __name__ == "__main__":
    success = asyncio.run(run_stability_and_memory_leak_test_async(iterations=1000))
    sys.exit(0 if success else 1)
