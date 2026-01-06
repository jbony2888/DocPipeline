"""
Local SQLite database for storing submission records.
Used for prototyping and review workflow.
"""

import sqlite3
import json
import os
from pathlib import Path
from typing import Optional, List, Dict
from datetime import datetime
from pipeline.schema import SubmissionRecord


# Use absolute path for database to ensure it works in Docker
# In Docker, use /app/data/submissions.db; locally, use ./submissions.db
if os.path.exists("/app"):
    # Running in Docker - use data directory
    data_dir = "/app/data"
    os.makedirs(data_dir, exist_ok=True)
    DB_PATH = os.path.join(data_dir, "submissions.db")
else:
    # Running locally
    DB_PATH = os.path.join(os.getcwd(), "submissions.db")


def init_database():
    """Initialize the SQLite database with the submissions table."""
    db_path = Path(DB_PATH)
    # Ensure the parent directory exists
    db_path.parent.mkdir(parents=True, exist_ok=True)
    
    try:
        # SQLite will create the file if it doesn't exist
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()
        
        # Create submissions table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS submissions (
                submission_id TEXT PRIMARY KEY,
                student_name TEXT,
                school_name TEXT,
                grade INTEGER,
                teacher_name TEXT,
                city_or_location TEXT,
                father_figure_name TEXT,
                phone TEXT,
                email TEXT,
                word_count INTEGER,
                ocr_confidence_avg REAL,
                needs_review BOOLEAN DEFAULT 0,
                review_reason_codes TEXT,
                artifact_dir TEXT,
                filename TEXT,
                owner_user_id TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Create index for owner_user_id
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_owner_user_id 
            ON submissions(owner_user_id)
        """)
        
        # Create index for faster queries
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_needs_review 
            ON submissions(needs_review)
        """)
        
        conn.commit()
        conn.close()
    except sqlite3.OperationalError as e:
        # If we can't create/open the file, try to create the directory and retry
        db_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            conn = sqlite3.connect(str(db_path))
            cursor = conn.cursor()
            
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS submissions (
                    submission_id TEXT PRIMARY KEY,
                    student_name TEXT,
                    school_name TEXT,
                    grade INTEGER,
                    teacher_name TEXT,
                    city_or_location TEXT,
                    father_figure_name TEXT,
                    phone TEXT,
                    email TEXT,
                    word_count INTEGER,
                    ocr_confidence_avg REAL,
                    needs_review BOOLEAN DEFAULT 0,
                    review_reason_codes TEXT,
                    artifact_dir TEXT,
                    filename TEXT,
                    owner_user_id TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_owner_user_id 
                ON submissions(owner_user_id)
            """)
            
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_needs_review 
                ON submissions(needs_review)
            """)
            
            conn.commit()
            conn.close()
        except Exception as e2:
            # If initialization fails, log error but don't crash
            print(f"Warning: Database initialization error (will retry on first use): {e2}")
    except Exception as e:
        # If initialization fails, log error but don't crash
        print(f"Warning: Database initialization error (will retry on first use): {e}")


def save_record(record: SubmissionRecord, filename: str = None, owner_user_id: str = None) -> bool:
    """
    Save a submission record to the database.
    
    Args:
        record: SubmissionRecord to save
        filename: Original filename (optional)
        owner_user_id: User ID of the teacher who owns this record (required)
        
    Returns:
        True if successful, False otherwise
    """
    if not owner_user_id:
        print("Error: owner_user_id is required to save a record")
        return False
    
    init_database()
    
    db_path = Path(DB_PATH)
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()
    
    try:
        cursor.execute("""
            INSERT OR REPLACE INTO submissions (
                submission_id, student_name, school_name, grade,
                teacher_name, city_or_location, father_figure_name,
                phone, email, word_count, ocr_confidence_avg,
                needs_review, review_reason_codes, artifact_dir,
                filename, owner_user_id, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            record.submission_id,
            record.student_name,
            record.school_name,
            record.grade,
            record.teacher_name,
            record.city_or_location,
            record.father_figure_name,
            record.phone,
            record.email,
            record.word_count,
            record.ocr_confidence_avg,
            1 if record.needs_review else 0,
            record.review_reason_codes,
            record.artifact_dir,
            filename,
            owner_user_id,
            datetime.now()
        ))
        
        conn.commit()
        return True
    except Exception as e:
        print(f"Error saving record to database: {e}")
        conn.rollback()
        return False
    finally:
        conn.close()


def get_records(needs_review: Optional[bool] = None, limit: int = 1000, owner_user_id: str = None) -> List[Dict]:
    """
    Get submission records from the database.
    
    Args:
        needs_review: Filter by needs_review status (None = all records)
        limit: Maximum number of records to return
        owner_user_id: Filter by owner user ID (required for multi-tenant security)
        
    Returns:
        List of record dictionaries
    """
    if not owner_user_id:
        print("Error: owner_user_id is required to query records")
        return []
    
    init_database()
    
    db_path = Path(DB_PATH)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row  # Access columns by name
    cursor = conn.cursor()
    
    if needs_review is None:
        cursor.execute("""
            SELECT * FROM submissions 
            WHERE owner_user_id = ?
            ORDER BY created_at DESC 
            LIMIT ?
        """, (owner_user_id, limit))
    else:
        cursor.execute("""
            SELECT * FROM submissions 
            WHERE owner_user_id = ? AND needs_review = ?
            ORDER BY created_at DESC 
            LIMIT ?
        """, (owner_user_id, 1 if needs_review else 0, limit))
    
    rows = cursor.fetchall()
    conn.close()
    
    # Convert rows to dictionaries
    records = []
    for row in rows:
        records.append({
            "submission_id": row["submission_id"],
            "student_name": row["student_name"],
            "school_name": row["school_name"],
            "grade": row["grade"],
            "teacher_name": row["teacher_name"],
            "city_or_location": row["city_or_location"],
            "father_figure_name": row["father_figure_name"],
            "phone": row["phone"],
            "email": row["email"],
            "word_count": row["word_count"],
            "ocr_confidence_avg": row["ocr_confidence_avg"],
            "needs_review": bool(row["needs_review"]),
            "review_reason_codes": row["review_reason_codes"],
            "artifact_dir": row["artifact_dir"],
            "filename": row["filename"],
            "owner_user_id": row.get("owner_user_id"),  # May be None for old records
            "created_at": row["created_at"],
            "updated_at": row["updated_at"]
        })
    
    return records


def get_record_by_id(submission_id: str, owner_user_id: str = None) -> Optional[Dict]:
    """
    Get a single record by submission_id.
    
    Args:
        submission_id: The submission ID to retrieve
        owner_user_id: User ID of the owner (required for security)
        
    Returns:
        Record dictionary if found and owned by user, None otherwise
    """
    if not owner_user_id:
        print("Error: owner_user_id is required to get a record")
        return None
    
    init_database()
    
    db_path = Path(DB_PATH)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    cursor.execute(
        "SELECT * FROM submissions WHERE submission_id = ? AND owner_user_id = ?",
        (submission_id, owner_user_id)
    )
    row = cursor.fetchone()
    conn.close()
    
    if row:
        return {
            "submission_id": row["submission_id"],
            "student_name": row["student_name"],
            "school_name": row["school_name"],
            "grade": row["grade"],
            "teacher_name": row["teacher_name"],
            "city_or_location": row["city_or_location"],
            "father_figure_name": row["father_figure_name"],
            "phone": row["phone"],
            "email": row["email"],
            "word_count": row["word_count"],
            "ocr_confidence_avg": row["ocr_confidence_avg"],
            "needs_review": bool(row["needs_review"]),
            "review_reason_codes": row["review_reason_codes"],
            "artifact_dir": row["artifact_dir"],
            "filename": row["filename"],
            "owner_user_id": row.get("owner_user_id"),
            "created_at": row["created_at"],
            "updated_at": row["updated_at"]
        }
    return None


def update_record(submission_id: str, updates: Dict, owner_user_id: str = None) -> bool:
    """
    Update a record in the database.
    
    Args:
        submission_id: The submission ID to update
        updates: Dictionary of fields to update
        owner_user_id: User ID of the owner (required for security)
        
    Returns:
        True if successful, False otherwise
    """
    if not owner_user_id:
        print("Error: owner_user_id is required to update a record")
        return False
    
    init_database()
    
    db_path = Path(DB_PATH)
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()
    
    # Build update query dynamically
    allowed_fields = [
        "student_name", "school_name", "grade", "teacher_name",
        "city_or_location", "father_figure_name", "phone", "email",
        "word_count", "ocr_confidence_avg", "needs_review", 
        "review_reason_codes"
    ]
    
    set_clauses = []
    values = []
    
    for field in allowed_fields:
        if field in updates:
            set_clauses.append(f"{field} = ?")
            if field == "needs_review":
                values.append(1 if updates[field] else 0)
            else:
                values.append(updates[field])
    
    if not set_clauses:
        conn.close()
        return False
    
    # Add updated_at timestamp
    set_clauses.append("updated_at = ?")
    values.append(datetime.now())
    # Add owner_user_id check to WHERE clause
    values.append(submission_id)
    values.append(owner_user_id)
    
    try:
        query = f"""
            UPDATE submissions 
            SET {', '.join(set_clauses)}
            WHERE submission_id = ? AND owner_user_id = ?
        """
        cursor.execute(query, values)
        conn.commit()
        return cursor.rowcount > 0
    except Exception as e:
        print(f"Error updating record: {e}")
        conn.rollback()
        return False
    finally:
        conn.close()


def delete_record(submission_id: str, owner_user_id: str = None) -> bool:
    """
    Delete a record from the database.
    
    Args:
        submission_id: The submission ID to delete
        owner_user_id: User ID of the owner (required for security)
        
    Returns:
        True if successful, False otherwise
    """
    if not owner_user_id:
        print("Error: owner_user_id is required to delete a record")
        return False
    
    init_database()
    
    db_path = Path(DB_PATH)
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()
    
    try:
        cursor.execute(
            "DELETE FROM submissions WHERE submission_id = ? AND owner_user_id = ?",
            (submission_id, owner_user_id)
        )
        conn.commit()
        return cursor.rowcount > 0
    except Exception as e:
        print(f"Error deleting record: {e}")
        conn.rollback()
        return False
    finally:
        conn.close()


def get_stats(owner_user_id: str = None) -> Dict:
    """
    Get statistics about records in the database.
    
    Args:
        owner_user_id: User ID of the owner (required for multi-tenant security)
        
    Returns:
        Dictionary with statistics
    """
    if not owner_user_id:
        return {
            "total_count": 0,
            "clean_count": 0,
            "needs_review_count": 0
        }
    
    init_database()
    
    db_path = Path(DB_PATH)
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()
    
    cursor.execute(
        "SELECT COUNT(*) FROM submissions WHERE owner_user_id = ? AND needs_review = 0",
        (owner_user_id,)
    )
    clean_count = cursor.fetchone()[0]
    
    cursor.execute(
        "SELECT COUNT(*) FROM submissions WHERE owner_user_id = ? AND needs_review = 1",
        (owner_user_id,)
    )
    needs_review_count = cursor.fetchone()[0]
    
    cursor.execute(
        "SELECT COUNT(*) FROM submissions WHERE owner_user_id = ?",
        (owner_user_id,)
    )
    total_count = cursor.fetchone()[0]
    
    conn.close()
    
    return {
        "total_count": total_count,
        "clean_count": clean_count,
        "needs_review_count": needs_review_count
    }

