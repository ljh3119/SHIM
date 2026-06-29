import datetime
from sqlalchemy import text

# List of migration functions to run sequentially
MIGRATIONS = []

def migration(version: str):
    def decorator(func):
        MIGRATIONS.append((version, func))
        return func
    return decorator

def run_all_migrations(engine):
    """Ensure schema_versions table exists and run all pending migrations."""
    with engine.connect() as conn:
        # 1. Create schema_versions table if not exists
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS schema_versions (
                version VARCHAR(100) PRIMARY KEY,
                applied_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """))
        conn.commit()
        
        # 2. Get applied migrations
        res = conn.execute(text("SELECT version FROM schema_versions"))
        applied = {row[0] for row in res.fetchall()}
        
        # 3. Run pending migrations in order
        for version, func in MIGRATIONS:
            if version not in applied:
                print(f"[MIGRATION] Running migration: {version}...")
                try:
                    # Run the migration functions
                    func(conn)
                    # Mark migration as applied
                    conn.execute(
                        text("INSERT INTO schema_versions (version) VALUES (:version)"),
                        {"version": version}
                    )
                    conn.commit()
                    print(f"[MIGRATION] Successfully applied: {version}")
                except Exception as e:
                    conn.rollback()
                    print(f"[MIGRATION ERROR] Failed to apply {version}: {e}")
                    raise e


@migration("v1_8_0_remove_legacy_is_admin")
def remove_legacy_is_admin(conn):
    # Check if is_admin column exists to prevent crash on fresh installs
    res = conn.execute(text("PRAGMA table_info(users)"))
    columns = [row[1] for row in res.fetchall()]
    if "is_admin" in columns:
        print("[MIGRATION] 'is_admin' 레거시 컬럼이 감지되어 물리적 삭제를 진행합니다.")
        conn.execute(text("ALTER TABLE users DROP COLUMN is_admin"))
        print("[MIGRATION] 'is_admin' 컬럼 삭제 완료.")


@migration("v1_8_5_system_metrics_columns")
def add_system_metrics_columns(conn):
    # system_settings 테이블 정보 조회
    res = conn.execute(text("PRAGMA table_info(system_settings)"))
    existing_cols = {row[1] for row in res.fetchall()}

    new_cols = {
        "last_backup_time": "DATETIME",
        "last_cleanup_time": "DATETIME",
        "last_backup_count": "INTEGER DEFAULT 0",
        "last_db_size_kb": "INTEGER DEFAULT 0"
    }

    for col_name, col_type in new_cols.items():
        if col_name not in existing_cols:
            conn.execute(text(f"ALTER TABLE system_settings ADD COLUMN {col_name} {col_type}"))


