"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { authFetch } from "@/lib/supabase/access-token";

type ProjectOption = { id: string; name: string };

type TerminalSession = {
  id: string;
  project_id: string;
  instance_id?: string | null;
  name?: string | null;
  status: string;
  created_at: string;
  updated_at: string;
};

type TerminalCommand = {
  id: string;
  session_id: string;
  command: string;
  status: string;
  exit_code?: number | null;
  created_at: string;
  started_at?: string | null;
  completed_at?: string | null;
};

type TerminalLog = {
  id: string;
  command_id: string;
  sequence: number;
  stream: "stdout" | "stderr";
  chunk: string;
  created_at: string;
};

function getErrorMessage(err: unknown, fallback: string): string {
  if (err instanceof Error && err.message) return err.message;
  return fallback;
}

export function TerminalConsole({ projects }: { projects: ProjectOption[] }) {
  const backendUrl = process.env.NEXT_PUBLIC_BACKEND_URL ?? "http://localhost:8000";
  const [selectedProjectId, setSelectedProjectId] = useState<string>(projects[0]?.id ?? "");

  const [sessions, setSessions] = useState<TerminalSession[]>([]);
  const [selectedSessionId, setSelectedSessionId] = useState<string>("");

  const [commands, setCommands] = useState<TerminalCommand[]>([]);
  const [activeCommandId, setActiveCommandId] = useState<string>("");
  const [logs, setLogs] = useState<TerminalLog[]>([]);
  const [afterSeq, setAfterSeq] = useState<number | null>(null);

  const [commandText, setCommandText] = useState("");
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [logIdlePolls, setLogIdlePolls] = useState(0);

  const selectedSession = useMemo(
    () => sessions.find((s) => s.id === selectedSessionId) ?? null,
    [sessions, selectedSessionId]
  );

  const fetchSessions = useCallback(async () => {
    if (!selectedProjectId) return;
    try {
      setErr(null);
      const res = await authFetch(`${backendUrl}/api/terminal/sessions/${selectedProjectId}`, { cache: "no-store" });
      const data = await res.json();
      if (!res.ok) throw new Error(data?.detail ?? "Failed to load sessions");
      const next = (data.sessions ?? []) as TerminalSession[];
      setSessions(next);
      if (!selectedSessionId && next[0]?.id) setSelectedSessionId(next[0].id);
      if (selectedSessionId && !next.some((s) => s.id === selectedSessionId)) {
        setSelectedSessionId(next[0]?.id ?? "");
      }
    } catch (e: unknown) {
      setErr(getErrorMessage(e, "Failed to load sessions"));
    }
  }, [backendUrl, selectedProjectId, selectedSessionId]);

  const fetchCommands = useCallback(async () => {
    if (!selectedSessionId) return;
    try {
      const res = await authFetch(`${backendUrl}/api/terminal/sessions/${selectedSessionId}/commands`, { cache: "no-store" });
      const data = await res.json();
      if (!res.ok) throw new Error(data?.detail ?? "Failed to load commands");
      const next = (data.commands ?? []) as TerminalCommand[];
      setCommands(next);
    } catch {
      // keep UI stable
    }
  }, [backendUrl, selectedSessionId]);

  const fetchLogs = useCallback(async () => {
    if (!activeCommandId) return;
    try {
      const params = new URLSearchParams();
      if (afterSeq !== null) params.set("after_sequence", String(afterSeq));
      params.set("limit", "200");
      const res = await authFetch(`${backendUrl}/api/terminal/commands/${activeCommandId}/logs?${params}`, { cache: "no-store" });
      const data = await res.json();
      if (!res.ok) return;
      const next = (data.logs ?? []) as TerminalLog[];
      if (next.length > 0) {
        setLogs((prev) => [...prev, ...next]);
        setAfterSeq(next[next.length - 1]!.sequence);
        setLogIdlePolls(0);
      } else {
        setLogIdlePolls((v) => v + 1);
      }
    } catch {
      // ignore
    }
  }, [backendUrl, activeCommandId, afterSeq]);

  useEffect(() => {
    fetchSessions();
    const t = setInterval(fetchSessions, 5000);
    return () => clearInterval(t);
  }, [fetchSessions]);

  useEffect(() => {
    setCommands([]);
    setActiveCommandId("");
    setLogs([]);
    setAfterSeq(null);
    if (!selectedSessionId) return;
    fetchCommands();
    const t = setInterval(fetchCommands, 3000);
    return () => clearInterval(t);
  }, [fetchCommands, selectedSessionId]);

  useEffect(() => {
    if (!activeCommandId) return;
    const active = commands.find((c) => c.id === activeCommandId);
    const isDone = active ? ["completed", "failed", "cancelled"].includes(active.status) : false;
    if (isDone && logIdlePolls >= 3) return;
    fetchLogs();
    const t = setInterval(fetchLogs, 2000);
    return () => clearInterval(t);
  }, [fetchLogs, activeCommandId, commands, logIdlePolls]);

  const createSession = async () => {
    if (!selectedProjectId) return;
    setLoading(true);
    try {
      setErr(null);
      const res = await authFetch(`${backendUrl}/api/terminal/sessions`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ project_id: selectedProjectId, name: "Project Terminal" }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data?.detail ?? "Failed to create session");
      await fetchSessions();
      if (data.session_id) setSelectedSessionId(data.session_id);
    } catch (e: unknown) {
      setErr(getErrorMessage(e, "Failed to create session"));
    } finally {
      setLoading(false);
    }
  };

  const runCommand = async () => {
    if (!selectedSessionId || !commandText.trim()) return;
    setLoading(true);
    try {
      setErr(null);
      const res = await authFetch(`${backendUrl}/api/terminal/sessions/${selectedSessionId}/commands`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ command: commandText }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data?.detail ?? "Failed to queue command");
      setCommandText("");
      setActiveCommandId(data.command_id);
      setLogs([]);
      setAfterSeq(null);
      setLogIdlePolls(0);
      await fetchCommands();
    } catch (e: unknown) {
      setErr(getErrorMessage(e, "Failed to queue command"));
    } finally {
      setLoading(false);
    }
  };

  const selectCommand = (id: string) => {
    setActiveCommandId(id);
    setLogs([]);
    setAfterSeq(null);
  };

  return (
    <div className="bg-dark-card border border-dark-border rounded-xl overflow-hidden">
      <div className="bg-black/40 px-4 py-2 border-b border-white/5 flex items-center justify-between">
        <span className="text-xs font-mono text-gray-500">TERMINAL</span>
        <div className="flex items-center gap-2">
          <select
            value={selectedProjectId}
            onChange={(e) => setSelectedProjectId(e.target.value)}
            className="text-xs font-mono bg-black/30 border border-white/10 rounded px-2 py-1 text-gray-300"
          >
            {projects.length > 0 ? (
              projects.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name}
                </option>
              ))
            ) : (
              <option value="">No projects</option>
            )}
          </select>
          <button
            onClick={createSession}
            disabled={loading || !selectedProjectId}
            className="text-xs font-mono px-2 py-1 rounded bg-white/5 hover:bg-white/10 border border-white/10 text-gray-300 disabled:opacity-50"
          >
            New session
          </button>
        </div>
      </div>

      <div className="p-4 space-y-3">
        {err && <div className="text-xs font-mono text-red-400">{err}</div>}

        <div className="flex items-center gap-2">
          <span className="text-xs font-mono text-gray-500">Session</span>
          <select
            value={selectedSessionId}
            onChange={(e) => setSelectedSessionId(e.target.value)}
            className="flex-1 text-xs font-mono bg-black/30 border border-white/10 rounded px-2 py-1 text-gray-300"
          >
            {sessions.map((s) => (
              <option key={s.id} value={s.id}>
                {(s.name ?? "Terminal").slice(0, 24)} • {s.status}
              </option>
            ))}
            {sessions.length === 0 && <option value="">No sessions</option>}
          </select>
          <span className="text-[10px] font-mono text-gray-600">
            {selectedSession?.instance_id ? "local agent connected" : "no local agent"}
          </span>
        </div>

        <div className="flex gap-2">
          <input
            value={commandText}
            onChange={(e) => setCommandText(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") runCommand();
            }}
            placeholder="Type a command (runs locally)"
            className="flex-1 text-sm font-mono bg-black/30 border border-white/10 rounded px-3 py-2 text-gray-200 placeholder:text-gray-600"
          />
          <button
            onClick={runCommand}
            disabled={loading || !selectedSessionId || !commandText.trim()}
            className="text-sm font-mono px-3 py-2 rounded bg-supabase-green text-black hover:bg-supabase-green-dark disabled:opacity-50"
          >
            Run
          </button>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-3">
          <div className="lg:col-span-1">
            <div className="text-xs font-mono text-gray-500 mb-2">History</div>
            <div className="max-h-64 overflow-auto space-y-1 pr-1">
              {commands.map((c) => (
                <button
                  key={c.id}
                  onClick={() => selectCommand(c.id)}
                  className={`w-full text-left text-xs font-mono px-2 py-2 rounded border ${
                    c.id === activeCommandId
                      ? "border-supabase-green/30 bg-supabase-green/10 text-supabase-green"
                      : "border-white/10 bg-black/20 text-gray-300 hover:bg-white/[0.03]"
                  }`}
                >
                  <div className="truncate">{c.command}</div>
                  <div className="text-[10px] text-gray-500">
                    {c.status}
                    {c.exit_code !== undefined && c.exit_code !== null ? ` • exit ${c.exit_code}` : ""}
                  </div>
                </button>
              ))}
              {commands.length === 0 && (
                <div className="text-xs font-mono text-gray-600 bg-black/20 border border-white/10 rounded p-3">
                  No commands yet.
                </div>
              )}
            </div>
          </div>

          <div className="lg:col-span-2">
            <div className="text-xs font-mono text-gray-500 mb-2">Output</div>
            <div className="h-64 overflow-auto bg-black/30 border border-white/10 rounded p-3 font-mono text-xs whitespace-pre-wrap text-gray-200">
              {activeCommandId ? (
                logs.length > 0 ? (
                  logs
                    .slice()
                    .sort((a, b) => a.sequence - b.sequence)
                    .map((l) => (l.stream === "stderr" ? `[stderr] ${l.chunk}` : l.chunk))
                    .join("")
                ) : (
                  <span className="text-gray-600">Waiting for output...</span>
                )
              ) : (
                <span className="text-gray-600">Select a command to view output.</span>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

