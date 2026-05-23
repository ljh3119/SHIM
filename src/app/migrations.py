import datetime
from sqlalchemy import text

# List of migration functions to run sequentially
MIGRATIONS = []

def migration(version: str):
    def decorator(func):
        MIGRATIONS.append((version, func))
        return func
    return decorator

@migration("v1_4_0_user_role_position")
def migrate_v1_4_0(conn):
    # Check columns in users table
    res = conn.execute(text("PRAGMA table_info(users)"))
    columns = [row[1] for row in res.fetchall()]
    
    if "role" not in columns:
        conn.execute(text("ALTER TABLE users ADD COLUMN role VARCHAR DEFAULT 'STAFF' NOT NULL"))
        print("[MIGRATION] Added column 'role' to 'users' table.")
    if "position" not in columns:
        conn.execute(text("ALTER TABLE users ADD COLUMN position VARCHAR(60) NULL"))
        print("[MIGRATION] Added column 'position' to 'users' table.")

@migration("v1_5_0_leaves_deductive_reason")
def migrate_v1_5_0(conn):
    # Check columns in leaves table
    res = conn.execute(text("PRAGMA table_info(leaves)"))
    columns = [row[1] for row in res.fetchall()]
    
    if "is_deductive" not in columns:
        conn.execute(text("ALTER TABLE leaves ADD COLUMN is_deductive BOOLEAN DEFAULT 1 NOT NULL"))
        print("[MIGRATION] Added column 'is_deductive' to 'leaves' table.")
    if "reason" not in columns:
        conn.execute(text("ALTER TABLE leaves ADD COLUMN reason VARCHAR(500) NULL"))
        print("[MIGRATION] Added column 'reason' to 'leaves' table.")

@migration("v1_5_6_system_settings_calendar")
def migrate_v1_5_6(conn):
    # Check columns in system_settings table
    res = conn.execute(text("PRAGMA table_info(system_settings)"))
    columns = [row[1] for row in res.fetchall()]
    
    if "company_calendar_visible" not in columns:
        conn.execute(text("ALTER TABLE system_settings ADD COLUMN company_calendar_visible BOOLEAN DEFAULT 0 NOT NULL"))
        print("[MIGRATION] Added column 'company_calendar_visible' to 'system_settings' table.")

@migration("v1_5_11_leaves_status_deductive_index")
def migrate_v1_5_11(conn):
    # SQLite supports CREATE INDEX IF NOT EXISTS
    conn.execute(text("CREATE INDEX IF NOT EXISTS ix_leaves_status_is_deductive ON leaves (status, is_deductive)"))
    print("[MIGRATION] Created index 'ix_leaves_status_is_deductive' on 'leaves' table.")

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
