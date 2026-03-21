"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { authFetch, getAuthHeader } from "@/lib/supabase/access-token";

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

function getErrorMessage(err: unknown, fallback: string): string {
  if (err instanceof Error && err.message) return err.message;
  return fallback;
}

export function UnifiedCommandCenter({
  projects,
  initialProvider = "cursor",
}: {
  projects: ProjectOption[];
  initialProvider?: "cursor" | "claude";
}) {
  const backendUrl = process.env.NEXT_PUBLIC_BACKEND_URL ?? "http://localhost:8000";
  const [selectedProjectId, setSelectedProjectId] = useState(projects[0]?.id ?? "");
  const [provider, setProvider] = useState<"cursor" | "claude">(initialProvider);
  const [prompt, setPrompt] = useState("");
  const [bashCommand, setBashCommand] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [voiceBusy, setVoiceBusy] = useState(false);
  const [isRecording, setIsRecording] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const [commands, setCommands] = useState<TimelineCommand[]>([]);
  const [activeCommandId, setActiveCommandId] = useState<string>("");
  const [logs, setLogs] = useState<TerminalLog[]>([]);

  const [timelineFilter, setTimelineFilter] = useState<"all" | "agentic" | "terminal">("all");

  const recorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);

  const filteredCommands = useMemo(() => {
    if (timelineFilter === "all") return commands;
    if (timelineFilter === "terminal") {
      return commands.filter((c) => (c.provider || "").toLowerCase() === "shell");
    }
    // agentic
    return commands.filter((c) => (c.provider || "").toLowerCase() !== "shell");
  }, [commands, timelineFilter]);

  const filteredActiveCommand = useMemo(
    () => filteredCommands.find((c) => c.id === activeCommandId) ?? null,
    [filteredCommands, activeCommandId]
  );

  useEffect(() => {
    const activeStillVisible =
      activeCommandId && filteredCommands.some((c) => c.id === activeCommandId);
    if (activeStillVisible) return;
    if (filteredCommands[0]?.id) setActiveCommandId(filteredCommands[0].id);
  }, [filteredCommands, activeCommandId]);

  const loadProvider = useCallback(async () => {
    try {
      const res = await authFetch(`${backendUrl}/api/settings/provider`, { cache: "no-store" });
      if (!res.ok) return;
      const json = await res.json();
      if (json?.provider === "cursor" || json?.provider === "claude") setProvider(json.provider);
    } catch { /* silent */ }
  }, [backendUrl]);

  const saveProvider = useCallback(
    async (nextProvider: string) => {
      try {
        await authFetch(`${backendUrl}/api/settings/provider`, {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ provider: nextProvider }),
        });
      } catch { /* silent */ }
    },
    [backendUrl]
  );

  const refreshTimeline = useCallback(async () => {
    try {
      const params = new URLSearchParams();
      params.set("limit", "100");
      if (selectedProjectId) params.set("project_id", selectedProjectId);
      const res = await authFetch(`${backendUrl}/api/unified/timeline?${params}`, { cache: "no-store" });
      if (!res.ok) return;
      const data = await res.json();
      const next = (data.commands ?? []) as TimelineCommand[];
      setCommands(next);
      if (!activeCommandId && next[0]?.id) setActiveCommandId(next[0].id);
    } catch { /* silent on polling */ }
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

  useEffect(() => {
    loadProvider();
  }, [loadProvider]);

  useEffect(() => {
    refreshTimeline();
    const interval = setInterval(() => {
      if (typeof document !== "undefined" && document.visibilityState !== "visible") return;
      refreshTimeline();
    }, 4000);
    return () => clearInterval(interval);
  }, [refreshTimeline]);

  useEffect(() => {
    setLogs([]);
    if (!activeCommandId) return;
    refreshLogs();
  }, [activeCommandId, refreshLogs]);

  useEffect(() => {
    if (!filteredActiveCommand) return;
    const done = ["completed", "failed", "cancelled"].includes(filteredActiveCommand.status);
    if (done) return;
    const interval = setInterval(refreshLogs, 2500);
    return () => clearInterval(interval);
  }, [filteredActiveCommand, refreshLogs]);

  const submitTyped = async () => {
    if (!selectedProjectId || !prompt.trim()) return;
    setSubmitting(true);
    setMessage(null);
    setError(null);
    try {
      const res = await authFetch(`${backendUrl}/api/unified/commands`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          project_id: selectedProjectId,
          prompt,
          source: "typed",
          provider,
        }),
      });
      const json = await res.json();
      if (!res.ok) throw new Error(json?.detail ?? "Failed to queue command");
      setPrompt("");
      setMessage(`Queued via ${json.provider}`);
      await refreshTimeline();
      if (json.command_id) setActiveCommandId(json.command_id);
    } catch (e: unknown) {
      setError(getErrorMessage(e, "Failed to queue command"));
    } finally {
      setSubmitting(false);
    }
  };

  const submitManualBash = async () => {
    if (!selectedProjectId || !bashCommand.trim()) return;
    setSubmitting(true);
    setMessage(null);
    setError(null);
    try {
      const res = await authFetch(`${backendUrl}/api/unified/commands`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          project_id: selectedProjectId,
          prompt: bashCommand,
          source: "typed",
          provider: "shell",
          session_name: "Manual Bash Terminal",
        }),
      });
      const json = await res.json();
      if (!res.ok) throw new Error(json?.detail ?? "Failed to queue bash command");
      setBashCommand("");
      setMessage("Queued manual bash command");
      await refreshTimeline();
      if (json.command_id) setActiveCommandId(json.command_id);
    } catch (e: unknown) {
      setError(getErrorMessage(e, "Failed to queue bash command"));
    } finally {
      setSubmitting(false);
    }
  };

  const startRecording = async () => {
    setMessage(null);
    setError(null);
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    const recorder = new MediaRecorder(stream);
    recorderRef.current = recorder;
    chunksRef.current = [];
    recorder.ondataavailable = (event) => {
      if (event.data.size > 0) chunksRef.current.push(event.data);
    };
    recorder.onstop = async () => {
      stream.getTracks().forEach((t) => t.stop());
      await submitVoice();
    };
    recorder.start();
    setIsRecording(true);
  };

  const stopRecording = () => {
    recorderRef.current?.stop();
    setIsRecording(false);
  };

  const submitVoice = async () => {
    setVoiceBusy(true);
    setError(null);
    setMessage(null);
    try {
      const auth = await getAuthHeader(true);
      if (!auth) throw new Error("No auth token. Please sign in again.");
      const blob = new Blob(chunksRef.current, { type: "audio/webm" });
      const formData = new FormData();
      formData.append("file", blob, "voice.webm");
      const res = await fetch(`${backendUrl}/transcribe`, {
        method: "POST",
        headers: { ...auth },
        body: formData,
      });
      const json = await res.json();
      if (!res.ok || json.status !== "success") {
        throw new Error(json?.message ?? "Voice command failed");
      }
      setMessage(json.action_result ?? "Voice command accepted.");
      await refreshTimeline();
    } catch (e: unknown) {
      setError(getErrorMessage(e, "Voice command failed"));
    } finally {
      setVoiceBusy(false);
    }
  };

  return (
    <section className="bg-dark-card border border-dark-border rounded-xl overflow-hidden">
      <div className="bg-black/40 px-4 py-2 border-b border-white/5">
        <span className="text-xs font-mono text-gray-500">UNIFIED COMMAND CENTER</span>
      </div>
      <div className="p-4 space-y-4">
        <div className="grid grid-cols-1 md:grid-cols-3 gap-2">
          <select
            value={selectedProjectId}
            onChange={(e) => setSelectedProjectId(e.target.value)}
            className="text-sm font-mono bg-black/30 border border-white/10 rounded px-2 py-2 text-gray-200"
          >
            {projects.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name}
              </option>
            ))}
          </select>
          <select
            value={provider}
            onChange={(e) => {
              const next = e.target.value as "cursor" | "claude";
              setProvider(next);
              saveProvider(next);
            }}
            className="text-sm font-mono bg-black/30 border border-white/10 rounded px-2 py-2 text-gray-200"
          >
            <option value="cursor">Cursor</option>
            <option value="claude">Claude</option>
          </select>
          <button
            onClick={isRecording ? stopRecording : startRecording}
            disabled={voiceBusy}
            className="text-sm font-mono px-3 py-2 rounded bg-white/5 hover:bg-white/10 border border-white/10 text-gray-300 disabled:opacity-50"
          >
            {isRecording ? "Stop recording" : voiceBusy ? "Processing voice..." : "Record voice"}
          </button>
        </div>

        <div className="flex gap-2">
          <input
            value={prompt}
            onChange={(e) => setPrompt(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") submitTyped();
            }}
            placeholder="Type what you want the coding agent to do"
            className="flex-1 text-sm font-mono bg-black/30 border border-white/10 rounded px-3 py-2 text-gray-200 placeholder:text-gray-600"
          />
          <button
            onClick={submitTyped}
            disabled={submitting || !prompt.trim()}
            className="text-sm font-mono px-3 py-2 rounded bg-supabase-green text-black hover:bg-supabase-green-dark disabled:opacity-50"
          >
            {submitting ? "Queueing..." : "Send"}
          </button>
        </div>

        <div className="border border-white/10 rounded p-3 bg-black/20">
          <div className="text-xs font-mono text-gray-400 mb-2">MANUAL BASH TERMINAL</div>
          <div className="flex gap-2">
            <input
              value={bashCommand}
              onChange={(e) => setBashCommand(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") submitManualBash();
              }}
              placeholder="Run a manual bash command (e.g. ls -la, pwd, git status)"
              className="flex-1 text-sm font-mono bg-black/30 border border-white/10 rounded px-3 py-2 text-gray-200 placeholder:text-gray-600"
            />
            <button
              onClick={submitManualBash}
              disabled={submitting || !bashCommand.trim()}
              className="text-sm font-mono px-3 py-2 rounded bg-white/10 text-gray-200 hover:bg-white/20 disabled:opacity-50"
            >
              Run Bash
            </button>
          </div>
        </div>

        {message && <div className="text-xs font-mono text-green-400">{message}</div>}
        {error && <div className="text-xs font-mono text-red-400">{error}</div>}

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-3">
          <div className="lg:col-span-1">
            <div className="text-xs font-mono text-gray-500 mb-2">Timeline</div>
            <div className="flex gap-2 mb-2">
              <button
                className={`text-[11px] font-mono px-2 py-1 rounded border ${
                  timelineFilter === "all"
                    ? "border-supabase-green/30 bg-supabase-green/10 text-supabase-green"
                    : "border-white/10 bg-black/20 text-gray-300 hover:bg-white/[0.03]"
                }`}
                onClick={() => setTimelineFilter("all")}
              >
                All ({commands.length})
              </button>
              <button
                className={`text-[11px] font-mono px-2 py-1 rounded border ${
                  timelineFilter === "agentic"
                    ? "border-supabase-green/30 bg-supabase-green/10 text-supabase-green"
                    : "border-white/10 bg-black/20 text-gray-300 hover:bg-white/[0.03]"
                }`}
                onClick={() => setTimelineFilter("agentic")}
              >
                Agentic ({commands.filter((c) => (c.provider || "").toLowerCase() !== "shell").length})
              </button>
              <button
                className={`text-[11px] font-mono px-2 py-1 rounded border ${
                  timelineFilter === "terminal"
                    ? "border-supabase-green/30 bg-supabase-green/10 text-supabase-green"
                    : "border-white/10 bg-black/20 text-gray-300 hover:bg-white/[0.03]"
                }`}
                onClick={() => setTimelineFilter("terminal")}
              >
                Terminal ({commands.filter((c) => (c.provider || "").toLowerCase() === "shell").length})
              </button>
            </div>
            <div className="max-h-80 overflow-auto space-y-1 pr-1">
              {filteredCommands.map((c) => (
                <button
                  key={c.id}
                  onClick={() => setActiveCommandId(c.id)}
                  className={`w-full text-left text-xs font-mono px-2 py-2 rounded border ${
                    c.id === activeCommandId
                      ? "border-supabase-green/30 bg-supabase-green/10 text-supabase-green"
                      : "border-white/10 bg-black/20 text-gray-300 hover:bg-white/[0.03]"
                  }`}
                >
                  <div className="truncate">{c.user_prompt || c.command}</div>
                  <div className="text-[10px] text-gray-500">
                    {(c.source || "typed").toUpperCase()} • {(c.provider || "shell").toUpperCase()} • {c.status}
                    {c.exit_code !== undefined && c.exit_code !== null ? ` • exit ${c.exit_code}` : ""}
                  </div>
                </button>
              ))}
              {filteredCommands.length === 0 && (
                <div className="text-xs font-mono text-gray-600 bg-black/20 border border-white/10 rounded p-3">
                  No commands yet.
                </div>
              )}
            </div>
          </div>

          <div className="lg:col-span-2">
            <div className="text-xs font-mono text-gray-500 mb-2">Output</div>
            <div className="h-80 overflow-auto bg-black/30 border border-white/10 rounded p-3 font-mono text-xs whitespace-pre-wrap text-gray-200">
              {filteredActiveCommand ? (
                <>
                  <div className="text-[11px] text-gray-500 mb-2">
                    {filteredActiveCommand?.provider === "shell" ? "Terminal Output" : "Agentic Coding Output"}
                  </div>
                  {logs.length > 0 ? (
                  logs
                    .slice()
                    .sort((a, b) => a.sequence - b.sequence)
                    .map((l) => {
                      if (l.stream !== "stderr") return l.chunk;
                      const failed =
                        filteredActiveCommand?.status === "failed" || filteredActiveCommand?.status === "cancelled";
                      return failed ? `[stderr] ${l.chunk}` : l.chunk;
                    })
                    .join("")
                  ) : (
                    <span className="text-gray-600">Waiting for output...</span>
                  )}
                </>
              ) : (
                <span className="text-gray-600">Select a command from the timeline.</span>
              )}
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
