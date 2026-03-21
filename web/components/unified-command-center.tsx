"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { authFetch } from "@/lib/supabase/access-token";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";

type ProjectOption = { id: string; name: string };

type TimelineCommand = {
  id: string;
  session_id: string;
  project_id: string;
  project_name?: string | null;
  command: string;
  source?: string | null;
  provider?: string | null;
  user_prompt?: string | null;
  status: string;
  exit_code?: number | null;
  created_at: string;
};

type TerminalLog = {
  id: string;
  sequence: number;
  stream: "stdout" | "stderr";
  chunk: string;
};

type CommandMode = "shell" | "agent";

function statusColor(status: string) {
  if (status === "completed") return "text-emerald-400";
  if (status === "running") return "text-blue-400";
  if (status === "queued") return "text-amber-400";
  if (status === "failed" || status === "cancelled") return "text-red-400";
  return "text-gray-400";
}

function statusDot(status: string) {
  if (status === "completed") return "bg-emerald-400";
  if (status === "running") return "bg-blue-400 animate-pulse";
  if (status === "queued") return "bg-amber-400";
  if (status === "failed" || status === "cancelled") return "bg-red-400";
  return "bg-gray-400";
}

function timeAgo(iso: string) {
  const seconds = Math.floor((Date.now() - new Date(iso).getTime()) / 1000);
  if (seconds < 60) return "just now";
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`;
  if (seconds < 86400) return `${Math.floor(seconds / 3600)}h ago`;
  return `${Math.floor(seconds / 86400)}d ago`;
}

export function UnifiedCommandCenter({
  projects,
}: {
  projects: ProjectOption[];
  initialProvider?: string;
}) {
  const backendUrl = process.env.NEXT_PUBLIC_BACKEND_URL ?? "http://localhost:8000";
  const [selectedProjectId, setSelectedProjectId] = useState(projects[0]?.id ?? "");
  const [agentProvider, setAgentProvider] = useState<"cursor" | "claude">("claude");
  const [mode, setMode] = useState<CommandMode>("agent");
  const [input, setInput] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const [commands, setCommands] = useState<TimelineCommand[]>([]);
  const [activeCommandId, setActiveCommandId] = useState<string>("");
  const [logs, setLogs] = useState<TerminalLog[]>([]);

  const logsEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const activeCommand = useMemo(
    () => commands.find((c) => c.id === activeCommandId) ?? null,
    [commands, activeCommandId]
  );

  const activeIsDone = useMemo(() => {
    if (!activeCommand) return false;
    return ["completed", "failed", "cancelled"].includes(activeCommand.status);
  }, [activeCommand]);

  // Load saved provider preference
  useEffect(() => {
    (async () => {
      try {
        const res = await authFetch(`${backendUrl}/api/settings/provider`, { cache: "no-store" });
        if (!res.ok) return;
        const json = await res.json();
        if (json?.provider === "cursor" || json?.provider === "claude") setAgentProvider(json.provider);
      } catch { /* silent */ }
    })();
  }, [backendUrl]);

  const refreshTimeline = useCallback(async () => {
    try {
      const params = new URLSearchParams({ limit: "50" });
      if (selectedProjectId) params.set("project_id", selectedProjectId);
      const res = await authFetch(`${backendUrl}/api/unified/timeline?${params}`, { cache: "no-store" });
      if (!res.ok) return;
      const data = await res.json();
      const next = (data.commands ?? []) as TimelineCommand[];
      setCommands(next);
      if (!activeCommandId && next[0]?.id) setActiveCommandId(next[0].id);
    } catch { /* silent */ }
  }, [activeCommandId, backendUrl, selectedProjectId]);

  const refreshLogs = useCallback(async () => {
    if (!activeCommandId) return;
    try {
      const res = await authFetch(`${backendUrl}/api/terminal/commands/${activeCommandId}/logs?limit=300`, { cache: "no-store" });
      if (!res.ok) return;
      const data = await res.json();
      setLogs((data.logs ?? []) as TerminalLog[]);
    } catch { /* silent */ }
  }, [activeCommandId, backendUrl]);

  // Poll timeline
  useEffect(() => {
    refreshTimeline();
    const interval = setInterval(() => {
      if (typeof document !== "undefined" && document.visibilityState !== "visible") return;
      refreshTimeline();
    }, 4000);
    return () => clearInterval(interval);
  }, [refreshTimeline]);

  // Load logs when active command changes
  useEffect(() => {
    setLogs([]);
    if (!activeCommandId) return;
    refreshLogs();
  }, [activeCommandId, refreshLogs]);

  // Poll logs while command is running
  useEffect(() => {
    if (!activeCommand) return;
    if (["completed", "failed", "cancelled"].includes(activeCommand.status)) return;
    const interval = setInterval(refreshLogs, 1500);
    return () => clearInterval(interval);
  }, [activeCommand, refreshLogs]);

  // Auto-scroll logs
  useEffect(() => {
    logsEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [logs]);

  // Auto-select first command when active is removed
  useEffect(() => {
    if (activeCommandId && commands.some((c) => c.id === activeCommandId)) return;
    if (commands[0]?.id) setActiveCommandId(commands[0].id);
  }, [commands, activeCommandId]);

  const submit = async () => {
    if (!selectedProjectId || !input.trim()) return;
    setSubmitting(true);
    setMessage(null);
    setError(null);
    try {
      const provider = mode === "shell" ? "shell" : agentProvider;
      const res = await authFetch(`${backendUrl}/api/unified/commands`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          project_id: selectedProjectId,
          prompt: input,
          source: "typed",
          provider,
        }),
      });
      const json = await res.json();
      if (!res.ok) throw new Error(json?.detail ?? "Failed to queue command");
      setInput("");
      setMessage(mode === "shell" ? "Command sent" : `Sent to ${provider}`);
      await refreshTimeline();
      if (json.command_id) setActiveCommandId(json.command_id);
      setTimeout(() => setMessage(null), 3000);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Failed to send command");
    } finally {
      setSubmitting(false);
      inputRef.current?.focus();
    }
  };

  const noProjects = projects.length === 0;

  if (noProjects) {
    return (
      <Card className="overflow-hidden">
        <CardContent className="py-8 text-center">
          <p className="text-sm text-muted-foreground">
            No projects yet. Create a project first to start sending commands.
          </p>
        </CardContent>
      </Card>
    );
  }

  return (
    <div className="space-y-3">
      {/* Command Input */}
      <Card className="overflow-hidden">
        <CardContent className="p-0">
          {/* Mode + Project selector bar */}
          <div className="flex items-center gap-1 px-3 py-2 border-b border-border bg-muted/30">
            <div className="flex rounded-md border border-border overflow-hidden mr-2">
              <button
                onClick={() => setMode("agent")}
                className={`px-3 py-1 text-xs font-mono transition-colors ${
                  mode === "agent"
                    ? "bg-primary text-primary-foreground"
                    : "bg-background text-muted-foreground hover:text-foreground"
                }`}
              >
                Agent
              </button>
              <button
                onClick={() => setMode("shell")}
                className={`px-3 py-1 text-xs font-mono transition-colors ${
                  mode === "shell"
                    ? "bg-primary text-primary-foreground"
                    : "bg-background text-muted-foreground hover:text-foreground"
                }`}
              >
                Shell
              </button>
            </div>

            <select
              value={selectedProjectId}
              onChange={(e) => setSelectedProjectId(e.target.value)}
              className="text-xs font-mono bg-background border border-border rounded px-2 py-1 text-foreground"
            >
              {projects.map((p) => (
                <option key={p.id} value={p.id}>{p.name}</option>
              ))}
            </select>

            {mode === "agent" && (
              <select
                value={agentProvider}
                onChange={(e) => {
                  const next = e.target.value as "cursor" | "claude";
                  setAgentProvider(next);
                  authFetch(`${backendUrl}/api/settings/provider`, {
                    method: "PUT",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ provider: next }),
                  }).catch(() => {});
                }}
                className="text-xs font-mono bg-background border border-border rounded px-2 py-1 text-foreground"
              >
                <option value="claude">Claude</option>
                <option value="cursor">Cursor</option>
              </select>
            )}

            <div className="flex-1" />

            {message && <span className="text-xs font-mono text-emerald-400">{message}</span>}
            {error && <span className="text-xs font-mono text-red-400">{error}</span>}
          </div>

          {/* Input */}
          <div className="flex">
            <span className="flex items-center px-3 text-sm font-mono text-muted-foreground select-none">
              {mode === "shell" ? "$" : ">"}
            </span>
            <input
              ref={inputRef}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => { if (e.key === "Enter") submit(); }}
              placeholder={
                mode === "shell"
                  ? "ls -la, git status, npm test ..."
                  : "Describe what you want the agent to do..."
              }
              className="flex-1 text-sm font-mono bg-transparent py-3 text-foreground placeholder:text-muted-foreground/50 focus:outline-none"
            />
            <button
              onClick={submit}
              disabled={submitting || !input.trim()}
              className="px-4 text-sm font-mono text-primary hover:text-primary/80 disabled:text-muted-foreground disabled:cursor-not-allowed transition-colors"
            >
              {submitting ? "..." : "Run"}
            </button>
          </div>
        </CardContent>
      </Card>

      {/* Timeline + Output */}
      {commands.length > 0 && (
        <div className="grid grid-cols-1 lg:grid-cols-[280px_1fr] gap-3">
          {/* Timeline */}
          <Card className="overflow-hidden">
            <div className="px-3 py-2 border-b border-border">
              <span className="text-xs font-medium text-muted-foreground">History</span>
            </div>
            <div className="max-h-[400px] overflow-auto">
              {commands.map((c) => (
                <button
                  key={c.id}
                  onClick={() => setActiveCommandId(c.id)}
                  className={`w-full text-left px-3 py-2.5 border-b border-border last:border-0 transition-colors ${
                    c.id === activeCommandId
                      ? "bg-accent"
                      : "hover:bg-accent/50"
                  }`}
                >
                  <div className="flex items-center gap-2">
                    <div className={`w-1.5 h-1.5 rounded-full shrink-0 ${statusDot(c.status)}`} />
                    <span className="text-xs font-mono truncate text-foreground">
                      {c.user_prompt || c.command}
                    </span>
                  </div>
                  <div className="flex items-center gap-2 mt-1 ml-3.5">
                    <Badge variant="outline" className="text-[10px] px-1 py-0 h-4">
                      {(c.provider || "shell")}
                    </Badge>
                    <span className="text-[10px] text-muted-foreground">{timeAgo(c.created_at)}</span>
                    {c.exit_code !== undefined && c.exit_code !== null && (
                      <span className={`text-[10px] ${c.exit_code === 0 ? "text-emerald-400" : "text-red-400"}`}>
                        exit {c.exit_code}
                      </span>
                    )}
                  </div>
                </button>
              ))}
            </div>
          </Card>

          {/* Output */}
          <Card className="overflow-hidden">
            <div className="px-3 py-2 border-b border-border flex items-center justify-between">
              <span className="text-xs font-medium text-muted-foreground">Output</span>
              {activeCommand && (
                <span className={`text-xs font-mono ${statusColor(activeCommand.status)}`}>
                  {activeCommand.status}
                </span>
              )}
            </div>
            <div className="h-[400px] overflow-auto p-3 font-mono text-xs whitespace-pre-wrap text-foreground bg-black/20">
              {activeCommand ? (
                <>
                  {logs.length > 0 ? (
                    logs
                      .slice()
                      .sort((a, b) => a.sequence - b.sequence)
                      .map((l, i) => (
                        <span key={l.id ?? i} className={l.stream === "stderr" ? "text-red-400" : ""}>
                          {l.chunk}
                        </span>
                      ))
                  ) : activeIsDone ? (
                    <span className="text-muted-foreground">
                      {activeCommand.status === "failed" ? "Command failed with no output." : "Completed with no output."}
                    </span>
                  ) : (
                    <span className="text-muted-foreground animate-pulse">Waiting for output...</span>
                  )}
                  <div ref={logsEndRef} />
                </>
              ) : (
                <span className="text-muted-foreground">Select a command from the history.</span>
              )}
            </div>
          </Card>
        </div>
      )}
    </div>
  );
}
