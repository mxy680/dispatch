"""Shared test fixtures – mocks the Supabase client so tests run without real credentials."""
from __future__ import annotations

import pytest
from unittest.mock import patch


class FakeResult:
    def __init__(self, data=None):
        self.data = data


class FakeQuery:
    def __init__(self, table_name: str, db: dict, action: str = "select"):
        self.table_name = table_name
        self.db = db
        self.action = action
        self.selected = "*"
        self.filters: list[tuple[str, str, object]] = []
        self.limit_count: int | None = None
        self.order_key: str | None = None
        self.order_desc = False
        self.single = False
        self.upsert_data: dict | None = None
        self.upsert_conflict: str | None = None
        self.insert_data: dict | None = None
        self.update_data: dict | None = None

    def select(self, columns="*"):
        self.selected = columns
        return self

    def eq(self, key: str, value: object):
        self.filters.append(("eq", key, value))
        return self

    def neq(self, key: str, value: object):
        self.filters.append(("neq", key, value))
        return self

    def ilike(self, key: str, pattern: str):
        self.filters.append(("ilike", key, pattern))
        return self

    def is_(self, key: str, value: str):
        self.filters.append(("is", key, value))
        return self

    def in_(self, key: str, values: list[object]):
        self.filters.append(("in", key, values))
        return self

    def gte(self, key: str, value: object):
        self.filters.append(("gte", key, value))
        return self

    def lt(self, key: str, value: object):
        self.filters.append(("lt", key, value))
        return self

    def order(self, key: str, desc: bool = False):
        self.order_key = key
        self.order_desc = desc
        return self

    def limit(self, n: int):
        self.limit_count = n
        return self

    def range(self, start: int, end: int):
        self.filters.append(("range", start, end))
        return self

    def maybe_single(self):
        self.single = True
        return self

    def insert(self, data: dict):
        self.action = "insert"
        self.insert_data = data
        return self

    def update(self, data: dict):
        self.action = "update"
        self.update_data = data
        return self

    def delete(self):
        self.action = "delete"
        return self

    def upsert(self, data: dict, on_conflict: str | None = None):
        self.action = "upsert"
        self.upsert_data = data
        self.upsert_conflict = on_conflict
        return self

    def execute(self):
        rows = list(self.db.get(self.table_name, []))

        def matches(row: dict) -> bool:
            for op, key, value in self.filters:
                actual = row.get(key)
                if op == "eq" and actual != value:
                    return False
                if op == "neq" and actual == value:
                    return False
                if op == "ilike":
                    if actual is None:
                        return False
                    if isinstance(value, str) and "%" in value:
                        if value.replace("%", "").lower() not in str(actual).lower():
                            return False
                    elif str(actual).lower() != str(value).lower():
                        return False
                if op == "is":
                    if value == "null":
                        if actual is not None:
                            return False
                    else:
                        if actual != value:
                            return False
                if op == "in" and actual not in value:
                    return False
                if op == "gte" and actual is not None and actual < value:
                    return False
                if op == "lt" and actual is not None and actual >= value:
                    return False
                if op == "range":
                    start, end = value, self.filters[-1][2] if self.filters else None
                    if start is not None and end is not None:
                        target = row.get("id")
                        if target is None or not (start <= target <= end):
                            return False
            return True

        if self.action == "insert":
            if self.insert_data is None:
                return FakeResult([])
            self.db.setdefault(self.table_name, []).append(dict(self.insert_data))
            return FakeResult(self.insert_data)

        if self.action == "update":
            updated = []
            for row in rows:
                if matches(row):
                    row.update(self.update_data or {})
                    updated.append(row)
            return FakeResult(updated)

        if self.action == "delete":
            remaining = [row for row in rows if not matches(row)]
            self.db[self.table_name] = remaining
            return FakeResult([])

        if self.action == "upsert":
            if self.upsert_data is None:
                return FakeResult([])
            conflict_keys = [k.strip() for k in (self.upsert_conflict or "").split(",") if k.strip()]
            existing = None
            if conflict_keys:
                for row in rows:
                    if all(row.get(key) == self.upsert_data.get(key) for key in conflict_keys):
                        existing = row
                        break
            if existing:
                existing.update(self.upsert_data)
                return FakeResult(existing)
            self.db.setdefault(self.table_name, []).append(dict(self.upsert_data))
            return FakeResult(self.upsert_data)

        if self.action == "select":
            results = [row for row in rows if matches(row)]
            if self.order_key:
                results.sort(key=lambda row: row.get(self.order_key), reverse=self.order_desc)
            if self.limit_count is not None:
                results = results[: self.limit_count]

            if self.single:
                return FakeResult(results[0] if results else None)

            if self.selected and self.selected != "*":
                if "terminal_sessions!inner" in self.selected:
                    output = []
                    for row in results:
                        session = next(
                            (s for s in self.db.get("terminal_sessions", []) if s.get("id") == row.get("session_id")),
                            None,
                        )
                        project = next(
                            (p for p in self.db.get("projects", []) if session and p.get("id") == session.get("project_id")),
                            None,
                        )
                        transformed = dict(row)
                        transformed["terminal_sessions"] = {
                            "project_id": session.get("project_id") if session else None,
                            "name": session.get("name") if session else None,
                            "projects": {"name": project.get("name")} if project else {},
                        }
                        output.append(transformed)
                    return FakeResult(output)
                keys = [part.strip().split("(")[0] for part in self.selected.replace("*", "").split(",") if part.strip()]
                return FakeResult([{k: row.get(k) for k in keys if k in row} for row in results])
            return FakeResult(results)

        return FakeResult([])


class FakeTable:
    def __init__(self, table_name: str, db: dict):
        self.table_name = table_name
        self.db = db

    def select(self, columns="*"):
        return FakeQuery(self.table_name, self.db, action="select").select(columns)

    def insert(self, data: dict):
        return FakeQuery(self.table_name, self.db, action="insert").insert(data)

    def update(self, data: dict):
        return FakeQuery(self.table_name, self.db, action="update").update(data)

    def delete(self):
        return FakeQuery(self.table_name, self.db, action="delete")

    def upsert(self, data: dict, on_conflict: str | None = None):
        return FakeQuery(self.table_name, self.db, action="upsert").upsert(data, on_conflict=on_conflict)


class FakeSupabaseClient:
    def __init__(self):
        self._tables: dict[str, list[dict]] = {}

    def table(self, table_name: str):
        return FakeTable(table_name, self._tables)

    def rpc(self, name: str, params: dict):
        return FakeResult([])


@pytest.fixture
def test_db():
    """Patch the Supabase client at the point where models import it."""
    fake_sb = FakeSupabaseClient()
    with patch("database.supabase_client.get_sb", return_value=fake_sb), patch("database.supabase_client._client", fake_sb):
        yield fake_sb
