from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any


def _http_json(
    *,
    method: str,
    url: str,
    body: dict[str, Any] | None = None,
    auth_token: str | None = None,
    agent_token: str | None = None,
    timeout_s: int = 30,
) -> dict[str, Any]:
    data = None
    headers = {"Content-Type": "application/json"}
    if auth_token:
        headers["Authorization"] = f"Bearer {auth_token}"
    if agent_token:
        headers["X-Agent-Token"] = agent_token
    if body is not None:
        data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:
            raw = resp.read().decode("utf-8")
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8") if hasattr(e, "read") else ""
        raise RuntimeError(f"HTTP {e.code} {method} {url}: {raw}") from e


@dataclass
class Config:
    backend_url: str
    project_id: str | None
    project_name: str | None
    project_path: str
    auth_token: str | None
    agent_token: str | None
    instance_token: str
    heartbeat_interval_s: int = 10
    poll_interval_s: float = 1.0
    claim_wait_seconds: int = 5
    log_chunk_bytes: int = 4000


def _chunk_text(s: str, max_bytes: int) -> list[str]:
    if not s:
        return []
    out: list[str] = []
    buf = ""
    for ch in s:
        buf += ch
        if len(buf.encode("utf-8")) >= max_bytes:
            out.append(buf)
            buf = ""
    if buf:
        out.append(buf)
    return out


def _is_cd_command(cmd: str) -> bool:
    s = cmd.strip()
    return s == "cd" or s.startswith("cd ")


def _apply_cd(cmd: str, current_dir: str, project_root: str) -> tuple[bool, str, str]:
    """
    Returns: (ok, new_cwd, message)
    """
    s = cmd.strip()
    if s == "cd":
        return True, project_root, f"cwd={project_root}\n"
    target = s[3:].strip()
    if not target:
        return True, project_root, f"cwd={project_root}\n"
    if os.path.isabs(target):
        new_dir = os.path.abspath(target)
    else:
        new_dir = os.path.abspath(os.path.join(current_dir, target))
    if os.path.isdir(new_dir):
        return True, new_dir, f"cwd={new_dir}\n"
    return False, current_dir, f"cd: no such directory: {target}\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Dispatch local agent daemon (terminal bridge)")
    parser.add_argument("--backend-url", required=True, help="Backend base URL, e.g. http://localhost:8000")
    parser.add_argument("--project-id", default=None, help="Project id (optional; backend can auto-create)")
    parser.add_argument("--project-name", default=None, help="Project name (optional; defaults to folder name)")
    parser.add_argument("--project-path", required=True, help="Absolute path to the local project directory")
    parser.add_argument("--auth-token", default=None, help="Supabase access token (JWT)")
    parser.add_argument("--agent-token", default=None, help="Dispatch agent token (from Settings)")
    parser.add_argument(
        "--instance-token",
        default=None,
        help="Stable token for this device/project (defaults to HOSTNAME-project)",
    )
    args = parser.parse_args()

    project_path = os.path.abspath(args.project_path)
    if not os.path.isdir(project_path):
        print(f"[local-agent] ERROR: project path not found: {project_path}", file=sys.stderr)
        return 2

    instance_token = args.instance_token or f"{os.uname().nodename}-{args.project_id}"
    cfg = Config(
        backend_url=args.backend_url.rstrip("/"),
        project_id=args.project_id,
        project_name=args.project_name,
        project_path=project_path,
        auth_token=args.auth_token,
        agent_token=args.agent_token,
        instance_token=instance_token,
    )

    print(f"[local-agent] backend={cfg.backend_url} project_id={cfg.project_id} project_path={cfg.project_path}")

    # Register instance
    reg = _http_json(
        method="POST",
        url=f"{cfg.backend_url}/api/agent/local/register",
        body={
            "project_id": cfg.project_id,
            "project_name": cfg.project_name,
            "project_path": cfg.project_path,
            "instance_token": cfg.instance_token,
            "pid": os.getpid(),
            "metadata": {
                "hostname": os.uname().nodename,
                "platform": sys.platform,
                "cwd": os.getcwd(),
                "project_path": cfg.project_path,
            },
        },
        auth_token=cfg.auth_token,
        agent_token=cfg.agent_token,
    )
    instance = (reg.get("instance") or {}) if isinstance(reg, dict) else {}
    instance_id = instance.get("id")
    if not instance_id:
        print(f"[local-agent] ERROR: register did not return instance id: {reg}", file=sys.stderr)
        return 3
    if isinstance(reg, dict) and reg.get("project_id"):
        cfg.project_id = str(reg["project_id"])
        print(f"[local-agent] registered project_id={cfg.project_id}")
    print(f"[local-agent] instance_id={instance_id}")

    last_heartbeat = 0.0
    next_sequence_by_command: dict[str, int] = {}
    session_cwd: dict[str, str] = {}
    idle_polls = 0

    while True:
        now = time.time()
        if now - last_heartbeat >= cfg.heartbeat_interval_s:
            try:
                _http_json(
                    method="POST",
                    url=f"{cfg.backend_url}/api/agent/local/heartbeat",
                    body={"instance_id": instance_id, "status": "online"},
                    auth_token=cfg.auth_token,
                    agent_token=cfg.agent_token,
                )
            except Exception as e:
                print(f"[local-agent] heartbeat failed: {e}", file=sys.stderr)
            last_heartbeat = now

        try:
            claim = _http_json(
                method="POST",
                url=f"{cfg.backend_url}/api/agent/local/claim-next",
                body={"instance_id": instance_id, "wait_seconds": cfg.claim_wait_seconds},
                auth_token=cfg.auth_token,
                agent_token=cfg.agent_token,
                timeout_s=max(30, cfg.claim_wait_seconds + 10),
            )
        except Exception as e:
            print(f"[local-agent] claim-next failed: {e}", file=sys.stderr)
            time.sleep(2)
            continue

        cmd = claim.get("command") if isinstance(claim, dict) else None
        if not cmd:
            idle_polls += 1
            # Back off when idle to reduce server load
            sleep_s = min(15.0, cfg.poll_interval_s + (idle_polls * 0.5))
            time.sleep(sleep_s)
            continue

        command_id = cmd.get("id")
        session_id = cmd.get("session_id")
        command_text = cmd.get("command") or ""
        if not command_id or not command_text or not session_id:
            time.sleep(cfg.poll_interval_s)
            continue

        idle_polls = 0

        print(f"[local-agent] running command_id={command_id} cmd={command_text!r}")

        cwd = session_cwd.get(session_id) or cfg.project_path
        stdout = ""
        stderr = ""
        exit_code = 0

        # Make `cd` persistent across commands (Cursor-like terminal semantics).
        if _is_cd_command(command_text):
            ok, new_cwd, msg = _apply_cd(command_text, cwd, cfg.project_path)
            if ok:
                session_cwd[session_id] = new_cwd
                stdout = msg
                exit_code = 0
            else:
                stderr = msg
                exit_code = 1
        else:
            # Execute command (non-interactive) inside the session cwd.
            proc = subprocess.Popen(
                command_text,
                cwd=cwd,
                shell=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            stdout, stderr = proc.communicate()
            exit_code = int(proc.returncode or 0)

        # Stream logs (chunked)
        seq = next_sequence_by_command.get(command_id, 0)
        try:
            for stream_name, text_data in (("stdout", stdout), ("stderr", stderr)):
                chunks = _chunk_text(text_data, cfg.log_chunk_bytes)
                if chunks:
                    _http_json(
                        method="POST",
                        url=f"{cfg.backend_url}/api/agent/local/commands/{command_id}/append-logs",
                        body={"sequence_start": seq, "stream": stream_name, "chunks": chunks},
                        auth_token=cfg.auth_token,
                        agent_token=cfg.agent_token,
                    )
                    seq += len(chunks)
        except Exception as e:
            print(f"[local-agent] append-logs failed: {e}", file=sys.stderr)

        next_sequence_by_command[command_id] = seq

        status = "completed" if exit_code == 0 else "failed"
        try:
            _http_json(
                method="POST",
                url=f"{cfg.backend_url}/api/agent/local/commands/{command_id}/complete",
                body={"status": status, "exit_code": exit_code},
                auth_token=cfg.auth_token,
                agent_token=cfg.agent_token,
            )
        except Exception as e:
            print(f"[local-agent] complete failed: {e}", file=sys.stderr)

        print(f"[local-agent] done command_id={command_id} status={status} exit_code={exit_code}")


if __name__ == "__main__":
    raise SystemExit(main())

