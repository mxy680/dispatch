"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { getAuthHeader } from "@/lib/supabase/access-token";
import { Card, CardHeader, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

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
      const auth = await getAuthHeader();
      if (!auth) return;
      const res = await fetch(`${backendUrl}/api/terminal/sessions/${selectedProjectId}`, {
        headers: { ...auth },
        cache: "no-store",
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data?.detail ?? "Failed to load sessions");
      const next = (data.sessions ?? []) as TerminalSession[];
      setSessions(next);
      if (!selectedSessionId && next[0]?.id) setSelectedSessionId(next[0].id);
      if (selectedSessionId && !next.some((s) => s.id === selectedSessionId)) {
        setSelectedSessionId(next[0]?.id ?? "");
      }
    } catch (e: any) {
      setErr(e?.message ?? "Failed to load sessions");
    }
  }, [backendUrl, selectedProjectId, selectedSessionId]);

  const fetchCommands = useCallback(async () => {
    if (!selectedSessionId) return;
    try {
      const auth = await getAuthHeader();
      if (!auth) return;
      const res = await fetch(`${backendUrl}/api/terminal/sessions/${selectedSessionId}/commands`, {
        headers: { ...auth },
        cache: "no-store",
      });
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
      const auth = await getAuthHeader();
      if (!auth) return;
      const params = new URLSearchParams();
      if (afterSeq !== null) params.set("after_sequence", String(afterSeq));
      params.set("limit", "200");
      const res = await fetch(`${backendUrl}/api/terminal/commands/${activeCommandId}/logs?${params}`, {
        headers: { ...auth },
        cache: "no-store",
      });
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
      const auth = await getAuthHeader();
      if (!auth) {
        setErr("Please sign in again.");
        return;
      }
      const res = await fetch(`${backendUrl}/api/terminal/sessions`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...auth },
        body: JSON.stringify({ project_id: selectedProjectId, name: "Project Terminal" }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data?.detail ?? "Failed to create session");
      await fetchSessions();
      if (data.session_id) setSelectedSessionId(data.session_id);
    } catch (e: any) {
      setErr(e?.message ?? "Failed to create session");
    } finally {
      setLoading(false);
    }
  };

  const runCommand = async () => {
    if (!selectedSessionId || !commandText.trim()) return;
    setLoading(true);
    try {
      setErr(null);
      const auth = await getAuthHeader();
      if (!auth) {
        setErr("Please sign in again.");
        return;
      }
      const res = await fetch(`${backendUrl}/api/terminal/sessions/${selectedSessionId}/commands`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...auth },
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
    } catch (e: any) {
      setErr(e?.message ?? "Failed to queue command");
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
    <Card className="h-full overflow-hidden">
      <CardHeader className="bg-black/40 px-4 py-2 border-b border-white/5 flex flex-row items-center justify-between space-y-0 pb-2">
        <span className="text-xs font-mono text-gray-500">TERMINAL</span>
        <div className="flex items-center gap-2">
          <Select value={selectedProjectId} onValueChange={setSelectedProjectId}>
            <SelectTrigger className="h-7 text-xs font-mono bg-black/30 border-white/10 text-gray-300 w-auto min-w-[120px]">
              <SelectValue placeholder="No projects" />
            </SelectTrigger>
            <SelectContent className="bg-dark-card border-dark-border">
              {projects.length > 0 ? (
                projects.map((p) => (
                  <SelectItem key={p.id} value={p.id} className="text-xs font-mono text-gray-300">
                    {p.name}
                  </SelectItem>
                ))
              ) : (
                <SelectItem value="none" disabled className="text-xs font-mono text-gray-500">
                  No projects
                </SelectItem>
              )}
            </SelectContent>
          </Select>
          <Button
            variant="outline"
            size="sm"
            onClick={createSession}
            disabled={loading || !selectedProjectId}
            className="h-7 text-xs font-mono bg-white/5 hover:bg-white/10 border-white/10 text-gray-300"
          >
            New session
          </Button>
        </div>
      </CardHeader>

      <CardContent className="p-4 space-y-3">
        {err && <div className="text-xs font-mono text-red-400">{err}</div>}

        <div className="flex items-center gap-2">
          <span className="text-xs font-mono text-gray-500">Session</span>
          <Select value={selectedSessionId} onValueChange={setSelectedSessionId}>
            <SelectTrigger className="flex-1 h-7 text-xs font-mono bg-black/30 border-white/10 text-gray-300">
              <SelectValue placeholder="No sessions" />
            </SelectTrigger>
            <SelectContent className="bg-dark-card border-dark-border">
              {sessions.map((s) => (
                <SelectItem key={s.id} value={s.id} className="text-xs font-mono text-gray-300">
                  {(s.name ?? "Terminal").slice(0, 24)} • {s.status}
                </SelectItem>
              ))}
              {sessions.length === 0 && (
                <SelectItem value="none" disabled className="text-xs font-mono text-gray-500">
                  No sessions
                </SelectItem>
              )}
            </SelectContent>
          </Select>
          <span className="text-[10px] font-mono text-gray-600">
            {selectedSession?.instance_id ? "local agent connected" : "no local agent"}
          </span>
        </div>

        <div className="flex gap-2">
          <Input
            value={commandText}
            onChange={(e) => setCommandText(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") runCommand();
            }}
            placeholder="Type a command (runs locally)"
            className="flex-1 text-sm font-mono bg-black/30 border-white/10 text-gray-200 placeholder:text-gray-600 focus-visible:ring-0 focus-visible:border-white/20"
          />
          <Button
            onClick={runCommand}
            disabled={loading || !selectedSessionId || !commandText.trim()}
            className="text-sm font-mono bg-supabase-green text-black hover:bg-supabase-green-dark"
          >
            Run
          </Button>
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
      </CardContent>
    </Card>
  );
}
