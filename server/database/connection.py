# server/database/connection.py
import sqlite3
import os
from pathlib import Path

# Saves dispatch.db in the 'server' folder
DB_PATH = Path(__file__).resolve().parent.parent / "dispatch.db"

def get_db_connection():
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn

def init_database():
    conn = get_db_connection()
    schema_path = Path(__file__).parent / "schema.sql"
    with open(schema_path, 'r') as f:
        conn.executescript(f.read())
    conn.commit()
    conn.close()
    print(f"✅ SQLite Database initialized at {DB_PATH}")

if __name__ == "__main__":
    init_database()