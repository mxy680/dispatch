"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { authFetch } from "@/lib/supabase/access-token";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { CommandLogViewer } from "@/components/command-log-viewer";

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

type CommandMode = "shell" | "agent";

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

  const inputRef = useRef<HTMLInputElement>(null);

  const activeCommand = useMemo(
    () => commands.find((c) => c.id === activeCommandId) ?? null,
    [commands, activeCommandId]
  );

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

  // Poll timeline
  useEffect(() => {
    refreshTimeline();
    const interval = setInterval(() => {
      if (typeof document !== "undefined" && document.visibilityState !== "visible") return;
      refreshTimeline();
    }, 4000);
    return () => clearInterval(interval);
  }, [refreshTimeline]);

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
              disabled={submitting || !input.trim() || !selectedProjectId}
              className="px-4 py-2 text-sm font-mono font-medium rounded-md bg-primary text-primary-foreground hover:bg-primary/90 disabled:bg-muted disabled:text-muted-foreground disabled:cursor-not-allowed transition-colors mr-1"
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

          <CommandLogViewer
            commandId={activeCommandId}
            commandStatus={activeCommand?.status ?? ""}
            height="400px"
          />
        </div>
      )}
    </div>
  );
}
