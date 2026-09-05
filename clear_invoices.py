import os
import sqlite3
from pathlib import Path

def clear_invoice_data():
    db_path = Path("invoices.db")
    if not db_path.exists():
        print("invoices.db not found!")
        return

    conn = sqlite3.connect(db_path, timeout=10.0)
    cursor = conn.cursor()

    # Enable foreign keys
    cursor.execute("PRAGMA foreign_keys = ON;")

    tables_to_clear = [
        "line_items",         # Child of invoices
        "invoice_reviews",    # Review decisions and approval records
        "invoice_revisions",  # Revision logs
        "invoices",           # Invoices
        "ingestion_log",      # Ingestion telemetry/logs
    ]

    cleared_counts = {}
    for table in tables_to_clear:
        cursor.execute(f"SELECT COUNT(*) FROM {table}")
        count = cursor.fetchone()[0]
        cursor.execute(f"DELETE FROM {table}")
        cleared_counts[table] = count
        print(f"Cleared {count} rows from {table}")

    # Reset SQLite autoincrement sequences
    try:
        for table in tables_to_clear:
            cursor.execute("DELETE FROM sqlite_sequence WHERE name = ?", (table,))
    except sqlite3.OperationalError:
        pass

    conn.commit()

    # VACUUM to reclaim space and rebuild index
    cursor.execute("VACUUM")
    conn.close()

    # Clean uploads directory so no stale uploaded files remain
    uploads_dir = Path("uploads")
    cleared_uploads = 0
    if uploads_dir.exists():
        for file_path in uploads_dir.glob("*"):
            if file_path.is_file():
                try:
                    file_path.unlink()
                    cleared_uploads += 1
                except Exception as e:
                    print(f"Failed to delete {file_path}: {e}")
        print(f"Cleared {cleared_uploads} files from uploads/")

    print("\nVerification of current database table counts:")
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    tables = [row[0] for row in c.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
    for t in tables:
        if t != 'sqlite_sequence':
            cnt = c.execute(f"SELECT count(*) FROM {t}").fetchone()[0]
            print(f"  {t}: {cnt}")
    conn.close()

if __name__ == "__main__":
    clear_invoice_data()
