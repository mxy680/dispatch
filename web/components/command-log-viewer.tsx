"use client";

import { useCallback, useEffect, useState } from "react";
import { authFetch } from "@/lib/supabase/access-token";
import { Card } from "@/components/ui/card";

type TerminalLog = {
  id: string;
  sequence: number;
  stream: "stdout" | "stderr";
  chunk: string;
};

const TERMINAL_STATUSES = ["completed", "failed", "cancelled"];

function statusColor(status: string) {
  if (status === "completed") return "text-emerald-400";
  if (status === "running") return "text-blue-400";
  if (status === "queued") return "text-amber-400";
  if (status === "failed" || status === "cancelled") return "text-red-400";
  return "text-gray-400";
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

  // Reset and load logs when commandId changes
  useEffect(() => {
    setLogs([]);
    if (!commandId) return;
    fetchLogs();
  }, [commandId, fetchLogs]);

  // Poll while not terminal
  useEffect(() => {
    if (!commandId || isTerminal) return;
    const interval = setInterval(() => {
      if (typeof document !== "undefined" && document.visibilityState !== "visible") return;
      fetchLogs();
    }, 1500);
    return () => clearInterval(interval);
  }, [commandId, isTerminal, fetchLogs]);

  function renderContent() {
    if (commandStatus === "queued" && logs.length === 0) {
      return (
        <span className="text-muted-foreground animate-pulse">
          Waiting for command to start...
        </span>
      );
    }

    if (logs.length > 0) {
      return logs
        .slice()
        .sort((a, b) => a.sequence - b.sequence)
        .map((l, i) => (
          <span key={l.id ?? i} className={l.stream === "stderr" ? "text-red-400" : ""}>
            {l.chunk}
          </span>
        ));
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
    <Card className="overflow-hidden">
      <div className="px-3 py-2 border-b border-border flex items-center justify-between">
        <span className="text-xs font-medium text-muted-foreground">Output</span>
        {commandStatus && (
          <span className={`text-xs font-mono ${statusColor(commandStatus)}`}>
            {commandStatus}
          </span>
        )}
      </div>
      <div
        className="overflow-auto p-3 font-mono text-xs whitespace-pre-wrap text-foreground bg-muted/50"
        style={{ height }}
      >
        {renderContent()}
      </div>
    </Card>
  );
}
