"use client";

import { useCallback, useEffect, useState, type ReactNode } from "react";
import { authFetch } from "@/lib/supabase/access-token";
import { Card } from "@/components/ui/card";

type TerminalLog = {
  id: string;
  sequence: number;
  stream: "stdout" | "stderr";
  chunk: string;
};

const TERMINAL_STATUSES = ["completed", "failed", "cancelled"];

// ── Structured log segment types ──

type Segment =
  | { kind: "text"; text: string }
  | { kind: "thinking"; text: string }
  | { kind: "tool_use"; name: string; input?: string }
  | { kind: "tool_result"; content: string; isError?: boolean }
  | { kind: "stderr"; text: string };

function parseAllLogs(logs: TerminalLog[]): Segment[] {
  const sorted = logs.slice().sort((a, b) => a.sequence - b.sequence);
  const segments: Segment[] = [];

  for (const log of sorted) {
    if (log.stream === "stderr") {
      segments.push({ kind: "stderr", text: log.chunk });
      continue;
    }

    const lines = log.chunk.split("\n").filter(Boolean);
    for (const line of lines) {
      let obj: Record<string, unknown>;
      try {
        obj = JSON.parse(line);
      } catch {
        // Plain text between JSON lines
        segments.push({ kind: "text", text: line + "\n" });
        continue;
      }

      if (obj.type === "system") continue; // skip init noise

      if (obj.type === "assistant" && obj.message) {
        const msg = obj.message as Record<string, unknown>;
        const content = msg.content as Array<Record<string, unknown>> | undefined;
        if (!content) continue;
        for (const block of content) {
          if (block.type === "thinking" && typeof block.thinking === "string") {
            segments.push({ kind: "thinking", text: block.thinking });
          } else if (block.type === "text" && typeof block.text === "string") {
            segments.push({ kind: "text", text: block.text });
          } else if (block.type === "tool_use" && typeof block.name === "string") {
            const input = block.input ? JSON.stringify(block.input, null, 2) : undefined;
            segments.push({ kind: "tool_use", name: block.name, input });
          }
        }
        continue;
      }

      if (obj.type === "user") {
        const msg = obj.message as Record<string, unknown> | undefined;
        const content = msg?.content as Array<Record<string, unknown>> | undefined;
        if (!content) continue;
        for (const block of content) {
          if (block.type === "tool_result") {
            const text =
              typeof block.content === "string"
                ? block.content
                : JSON.stringify(block.content);
            segments.push({
              kind: "tool_result",
              content: text.slice(0, 2000),
              isError: block.is_error === true,
            });
          }
        }
        continue;
      }

      if (obj.type === "result" && typeof obj.result === "string") {
        segments.push({ kind: "text", text: obj.result });
        continue;
      }

      // Fallback: skip rate_limit_event noise and other meta events
      if (obj.type === "rate_limit_event") continue;

      // Plain text after JSON objects (e.g. Claude's final text output)
      if (typeof obj.content === "string") {
        segments.push({ kind: "text", text: obj.content });
      }
    }
  }
  return segments;
}

function statusColor(status: string) {
  if (status === "completed") return "text-emerald-400";
  if (status === "running") return "text-blue-400";
  if (status === "queued") return "text-amber-400";
  if (status === "failed" || status === "cancelled") return "text-red-400";
  return "text-gray-400";
}

function SegmentView({ seg }: { seg: Segment }) {
  switch (seg.kind) {
    case "text":
      return <div className="whitespace-pre-wrap break-words">{seg.text}</div>;

    case "thinking":
      return (
        <details className="my-2 rounded border border-zinc-700 bg-zinc-800/50">
          <summary className="cursor-pointer select-none px-3 py-1.5 text-[11px] font-medium text-zinc-400 hover:text-zinc-300">
            Thinking…
          </summary>
          <div className="px-3 py-2 text-[11px] text-zinc-500 whitespace-pre-wrap break-words border-t border-zinc-700">
            {seg.text}
          </div>
        </details>
      );

    case "tool_use":
      return (
        <div className="my-2 rounded border border-blue-900/50 bg-blue-950/30">
          <div className="px-3 py-1.5 text-[11px] font-semibold text-blue-400 flex items-center gap-1.5">
            <span className="inline-block w-1.5 h-1.5 rounded-full bg-blue-400" />
            {seg.name}
          </div>
          {seg.input && (
            <pre className="px-3 py-2 text-[10px] text-zinc-400 overflow-x-auto border-t border-blue-900/50 max-h-40">
              {seg.input}
            </pre>
          )}
        </div>
      );

    case "tool_result":
      return (
        <div
          className={`my-1 rounded border px-3 py-2 text-[11px] overflow-x-auto max-h-40 whitespace-pre-wrap break-words ${
            seg.isError
              ? "border-red-900/50 bg-red-950/20 text-red-400"
              : "border-zinc-700/50 bg-zinc-900/30 text-zinc-400"
          }`}
        >
          {seg.content}
        </div>
      );

    case "stderr":
      return (
        <div className="text-red-400 whitespace-pre-wrap break-words">{seg.text}</div>
      );

    default:
      return null;
  }
}

export function CommandLogViewer({
  commandId,
  commandStatus,
  height = "300px",
}: {
  commandId: string;
  commandStatus: string;
  height?: string;
}) {
  const backendUrl = process.env.NEXT_PUBLIC_BACKEND_URL ?? "http://localhost:8000";
  const [logs, setLogs] = useState<TerminalLog[]>([]);
  const isTerminal = TERMINAL_STATUSES.includes(commandStatus);
  const isDone = isTerminal;

  const fetchLogs = useCallback(async () => {
    if (!commandId) return;
    try {
      const res = await authFetch(
        `${backendUrl}/api/terminal/commands/${commandId}/logs?limit=300`,
        { cache: "no-store" }
      );
      if (!res.ok) return;
      const data = await res.json();
      setLogs((data.logs ?? []) as TerminalLog[]);
    } catch {
      /* silent */
    }
  }, [commandId, backendUrl]);

  useEffect(() => {
    setLogs([]);
    if (!commandId) return;
    fetchLogs();
  }, [commandId, fetchLogs]);

  useEffect(() => {
    if (!commandId || isTerminal) return;
    const interval = setInterval(() => {
      if (typeof document !== "undefined" && document.visibilityState !== "visible") return;
      fetchLogs();
    }, 1500);
    return () => clearInterval(interval);
  }, [commandId, isTerminal, fetchLogs]);

  function renderContent(): ReactNode {
    if (commandStatus === "queued" && logs.length === 0) {
      return (
        <span className="text-muted-foreground animate-pulse">
          Waiting for command to start...
        </span>
      );
    }

    if (logs.length > 0) {
      const segments = parseAllLogs(logs);
      if (segments.length === 0) {
        return <span className="text-muted-foreground">Processing…</span>;
      }
      return segments.map((seg, i) => <SegmentView key={i} seg={seg} />);
    }

    if (isDone) {
      if (commandStatus === "failed") {
        return (
          <span className="text-muted-foreground">Command failed with no output.</span>
        );
      }
      return <span className="text-muted-foreground">Completed with no output.</span>;
    }

    return (
      <span className="text-muted-foreground animate-pulse">Waiting for output...</span>
    );
  }

  return (
    <Card className="overflow-hidden min-w-0">
      <div className="px-3 py-2 border-b border-border flex items-center justify-between">
        <span className="text-xs font-medium text-muted-foreground">Output</span>
        {commandStatus && (
          <span className={`text-xs font-mono ${statusColor(commandStatus)}`}>
            {commandStatus}
          </span>
        )}
      </div>
      <div
        className="overflow-auto p-3 font-mono text-xs text-foreground bg-muted/50"
        style={{ height, maxWidth: "100%" }}
      >
        {renderContent()}
      </div>
    </Card>
  );
}
