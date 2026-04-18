from pathlib import Path
import sqlite3

BASE_DIR = Path(__file__).resolve().parent
DB_FILE = BASE_DIR / "database.db"

DB_FILE.parent.mkdir(parents=True, exist_ok=True)
conn = sqlite3.connect(DB_FILE)
cursor = conn.cursor()

cursor.execute(
    """
CREATE TABLE IF NOT EXISTS user_info (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    type INTEGER NOT NULL,
    filePath TEXT NOT NULL,
    userName TEXT NOT NULL,
    status INTEGER DEFAULT 0
)
"""
)

cursor.execute(
    """
CREATE TABLE IF NOT EXISTS file_records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    filename TEXT NOT NULL,
    filesize REAL,
    upload_time DATETIME DEFAULT CURRENT_TIMESTAMP,
    file_path TEXT,
    source_url TEXT,
    source_type TEXT,
    video_title TEXT,
    video_title_zh TEXT,
    video_description TEXT
)
"""
)

cursor.execute("PRAGMA table_info(file_records)")
columns = {row[1] for row in cursor.fetchall()}
for column_name, column_type in [
    ("source_url", "TEXT"),
    ("source_type", "TEXT"),
    ("video_title", "TEXT"),
    ("video_title_zh", "TEXT"),
    ("video_description", "TEXT"),
]:
    if column_name not in columns:
        cursor.execute(f"ALTER TABLE file_records ADD COLUMN {column_name} {column_type}")

cursor.execute(
    """
CREATE TABLE IF NOT EXISTS system_settings (
    setting_key TEXT PRIMARY KEY,
    setting_value TEXT
)
"""
)

conn.commit()
conn.close()
print(f"Tables initialized: {DB_FILE}")
