
import sqlite3
import os

db_path = "var/data/shim_internal.db"

if not os.path.exists(db_path):
    print(f"Database not found at {db_path}")
else:
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Check current columns
    cursor.execute("PRAGMA table_info(leaves)")
    columns = [row[1] for row in cursor.fetchall()]
    print(f"Current columns in 'leaves': {columns}")
    
    needed = [
        ("is_deductive", "BOOLEAN DEFAULT 1 NOT NULL"),
        ("reason", "VARCHAR(500)")
    ]
    
    for col_name, col_def in needed:
        if col_name not in columns:
            print(f"Adding column {col_name}...")
            try:
                cursor.execute(f"ALTER TABLE leaves ADD COLUMN {col_name} {col_def}")
                print(f"Successfully added {col_name}")
            except Exception as e:
                print(f"Error adding {col_name}: {e}")
        else:
            print(f"Column {col_name} already exists.")
            
    conn.commit()
    conn.close()
    print("Migration check complete.")
