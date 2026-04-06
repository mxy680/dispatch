# server/database/sidecar_store.py
"""
Local-only SQLite store for approval-gate UX: conversation turns, dialogue state,
and per-command risk assessment. Supabase schema stays unchanged (no new tables/columns).

Path: DISPATCH_SIDECAR_PATH or server/data/dispatch_sidecar.db
"""
from __future__ import annotations

import json
import os
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path

def _sidecar_path() -> Path:
    env = os.environ.get("DISPATCH_SIDECAR_PATH")
    if env:
        return Path(env)
    return Path(__file__).resolve().parent.parent / "data" / "dispatch_sidecar.db"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _conn() -> sqlite3.Connection:
    path = _sidecar_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(str(path))
    c.row_factory = sqlite3.Row
    return c


def _init(c: sqlite3.Connection) -> None:
    c.executescript(
        """
        CREATE TABLE IF NOT EXISTS conversation_turns (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            project_id TEXT,
            session_id TEXT,
            command_id TEXT,
            role TEXT NOT NULL,
            turn_type TEXT NOT NULL,
            content TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_sidecar_turns_user_proj_created
            ON conversation_turns(user_id, project_id, created_at);

        CREATE TABLE IF NOT EXISTS conversation_state (
            user_id TEXT NOT NULL,
            project_id TEXT NOT NULL DEFAULT '',
            state TEXT NOT NULL,
            active_command_id TEXT,
            context_json TEXT NOT NULL DEFAULT '{}',
            updated_at TEXT NOT NULL,
            PRIMARY KEY (user_id, project_id)
        );

        CREATE TABLE IF NOT EXISTS command_risk (
            command_id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            risk_level TEXT NOT NULL,
            risk_reason TEXT,
            plain_summary TEXT,
            updated_at TEXT NOT NULL
        );
        """
    )
    c.commit()


def _ensure(c: sqlite3.Connection) -> None:
    _init(c)
    cols = {
        r["name"] for r in c.execute("PRAGMA table_info(command_risk)").fetchall()
    }
    if "plain_summary" not in cols:
        c.execute("ALTER TABLE command_risk ADD COLUMN plain_summary TEXT")
        c.commit()


def _project_key(project_id: str | None) -> str:
    return project_id or ""


def add_conversation_turn(
    *,
    user_id: str,
    project_id: str | None,
    session_id: str | None,
    command_id: str | None,
    role: str,
    turn_type: str,
    content: str,
) -> dict:
    turn_id = str(uuid.uuid4())
    row = {
        "id": turn_id,
        "user_id": user_id,
        "project_id": project_id,
        "session_id": session_id,
        "command_id": command_id,
        "role": role,
        "turn_type": turn_type,
        "content": content,
        "created_at": _now_iso(),
    }
    with _conn() as c:
        _ensure(c)
        c.execute(
            """INSERT INTO conversation_turns
            (id, user_id, project_id, session_id, command_id, role, turn_type, content, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                row["id"],
                row["user_id"],
                row["project_id"],
                row["session_id"],
                row["command_id"],
                row["role"],
                row["turn_type"],
                row["content"],
                row["created_at"],
            ),
        )
        c.commit()
    return row


def list_conversation_turns_for_user(*, user_id: str, project_id: str | None = None, limit: int = 100) -> list[dict]:
    with _conn() as c:
        _ensure(c)
        if project_id is not None:
            cur = c.execute(
                """SELECT * FROM conversation_turns WHERE user_id = ? AND project_id = ?
                ORDER BY created_at DESC LIMIT ?""",
                (user_id, project_id, limit),
            )
        else:
            cur = c.execute(
                "SELECT * FROM conversation_turns WHERE user_id = ? ORDER BY created_at DESC LIMIT ?",
                (user_id, limit),
            )
        rows = [dict(r) for r in cur.fetchall()]
    return list(reversed(rows))


def get_conversation_state(*, user_id: str, project_id: str | None) -> dict | None:
    pk = _project_key(project_id)
    with _conn() as c:
        _ensure(c)
        cur = c.execute(
            "SELECT * FROM conversation_state WHERE user_id = ? AND project_id = ?",
            (user_id, pk),
        )
        r = cur.fetchone()
    if not r:
        return None
    d = dict(r)
    d["id"] = f"{d['user_id']}:{d['project_id']}"
    return d


def upsert_conversation_state(
    *,
    user_id: str,
    project_id: str | None,
    state: str,
    active_command_id: str | None,
    context_json: dict | None = None,
) -> dict:
    pk = _project_key(project_id)
    ctx = json.dumps(context_json or {})
    now = _now_iso()
    with _conn() as c:
        _ensure(c)
        c.execute(
            """INSERT INTO conversation_state (user_id, project_id, state, active_command_id, context_json, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(user_id, project_id) DO UPDATE SET
              state = excluded.state,
              active_command_id = excluded.active_command_id,
              context_json = excluded.context_json,
              updated_at = excluded.updated_at""",
            (user_id, pk, state, active_command_id, ctx, now),
        )
        c.commit()
    out = get_conversation_state(user_id=user_id, project_id=project_id)
    return out or {
        "id": f"{user_id}:{pk}",
        "user_id": user_id,
        "project_id": None if pk == "" else pk,
        "state": state,
        "active_command_id": active_command_id,
        "context_json": ctx,
        "updated_at": now,
    }


def set_command_risk(
    *,
    command_id: str,
    user_id: str,
    risk_level: str,
    risk_reason: str | None,
    plain_summary: str | None = None,
) -> None:
    level = (risk_level or "PENDING").strip().upper()
    if level not in {"PENDING", "SAFE", "WARNING", "HIGH_RISK"}:
        level = "WARNING"
    now = _now_iso()
    with _conn() as c:
        _ensure(c)
        c.execute(
            """INSERT INTO command_risk (command_id, user_id, risk_level, risk_reason, plain_summary, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(command_id) DO UPDATE SET
              risk_level = excluded.risk_level,
              risk_reason = excluded.risk_reason,
              plain_summary = excluded.plain_summary,
              updated_at = excluded.updated_at,
              user_id = excluded.user_id""",
            (command_id, user_id, level, risk_reason, plain_summary, now),
        )
        c.commit()


def reset_command_risk_pending(*, command_id: str, user_id: str) -> None:
    set_command_risk(
        command_id=command_id,
        user_id=user_id,
        risk_level="PENDING",
        risk_reason=None,
        plain_summary="I prepared this action and I am waiting for your approval before I run it.",
    )


def get_command_risk(command_id: str) -> dict | None:
    with _conn() as c:
        _ensure(c)
        cur = c.execute("SELECT * FROM command_risk WHERE command_id = ?", (command_id,))
        r = cur.fetchone()
    return dict(r) if r else None


def enrich_command(cmd: dict | None) -> dict | None:
    if not cmd:
        return None
    cid = cmd.get("id")
    if not cid:
        return cmd
    r = get_command_risk(cid)
    if r:
        return {
            **cmd,
            "risk_level": r["risk_level"],
            "risk_reason": r.get("risk_reason"),
            "plain_summary": r.get("plain_summary"),
        }
    return {**cmd, "risk_level": "PENDING", "risk_reason": None, "plain_summary": None}


def enrich_commands(commands: list[dict]) -> list[dict]:
    out: list[dict] = []
    for c in commands:
        enriched = enrich_command(dict(c))
        out.append(enriched if enriched is not None else c)
    return out
