"""
Database migration utilities.
"""

import sqlite3
from pathlib import Path
from pipeline.database import DB_PATH


def migrate_add_owner_user_id():
    """
    Add owner_user_id column to submissions table if it doesn't exist.
    This migration is safe to run multiple times (idempotent).
    """
    db_path = Path(DB_PATH)
    if not db_path.exists():
        # Database doesn't exist yet, will be created with column in init_database
        return True
    
    try:
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()
        
        # Check if column exists
        cursor.execute("PRAGMA table_info(submissions)")
        columns = [row[1] for row in cursor.fetchall()]
        
        if "owner_user_id" not in columns:
            # Add column
            cursor.execute("""
                ALTER TABLE submissions 
                ADD COLUMN owner_user_id TEXT
            """)
            
            # Create index for faster queries
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_owner_user_id 
                ON submissions(owner_user_id)
            """)
            
            conn.commit()
            print("✅ Migration completed: Added owner_user_id column")
        else:
            print("ℹ️ Migration skipped: owner_user_id column already exists")
        
        conn.close()
        return True
    except Exception as e:
        print(f"❌ Migration error: {e}")
        return False





