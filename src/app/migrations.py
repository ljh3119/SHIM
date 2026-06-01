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

