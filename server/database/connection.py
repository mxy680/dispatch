# server/database/connection.py
import sqlite3
import os
from pathlib import Path

# Get the database file path
DB_DIR = Path(__file__).parent.parent  # Goes up to 'server' folder
DB_PATH = DB_DIR / "dispatch.db"

def get_db_connection():
    """
    Create and return a connection to the SQLite database.
    """
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row  # This lets us access columns by name
    return conn

def init_database():
    """
    Initialize the database by running the schema.sql file.
    Creates all tables if they don't exist.
    """
    conn = get_db_connection()
    
    # Read the schema file
    schema_path = Path(__file__).parent / "schema.sql"
    with open(schema_path, 'r') as f:
        schema_sql = f.read()
    
    # Execute the schema
    conn.executescript(schema_sql)
    conn.commit()
    conn.close()
    
    print(f"✅ Database initialized at {DB_PATH}")

# Run initialization when this module is imported
if __name__ == "__main__":
    init_database()