import pytest
import sqlite3
import os
from unittest.mock import patch


@pytest.fixture
def test_db(tmp_path):
    """Create a temporary test database."""
    db_path = tmp_path / "test.db"

    # Read and execute schema
    schema_path = os.path.join(os.path.dirname(__file__), "..", "database", "schema.sql")
    with open(schema_path) as f:
        schema_sql = f.read()

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.executescript(schema_sql)
    conn.commit()
    conn.close()

    def get_test_connection():
        c = sqlite3.connect(str(db_path))
        c.row_factory = sqlite3.Row
        return c

    with patch("database.models.get_db_connection", side_effect=get_test_connection):
        yield get_test_connection
