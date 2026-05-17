import sys
from pathlib import Path

# 소스 경로 추가
sys.path.append(str(Path(__file__).resolve().parents[2] / "src"))

from app import models, database, auth
from app.database import SessionLocal

def reset_admin_password():
    db = SessionLocal()
    try:
        admin = db.query(models.Users).filter(models.Users.user_id == "admin").first()
        if not admin:
            print("[오류] 'admin' 계정이 존재하지 않습니다.")
            return

        # 비밀번호를 '0000'으로 초기화
        new_hash = auth.get_password_hash("0000")
        admin.password = new_hash
        
        # 감사 로그 기록 (누가 했는지 알 수 없으므로 시스템으로 기록)
        db.add(models.AuditLogs(
            actor_id="system",
            action="RESET_ADMIN_PASSWORD",
            target_info="Admin:admin",
            old_data="*****",
            new_data="0000 (Emergency Reset)"
        ))
        
        db.commit()
        print("[성공] 'admin' 계정의 비밀번호가 '0000'으로 초기화되었습니다.")
        print("로그인 후 반드시 비밀번호를 변경해 주세요.")
    except Exception as e:
        db.rollback()
        print(f"[오류] 초기화 중 문제가 발생했습니다: {str(e)}")
    finally:
        db.close()

if __name__ == "__main__":
    reset_admin_password()
