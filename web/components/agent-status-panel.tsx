"use client";
import { useState, useEffect } from "react";
import { Card, CardHeader, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";

type AgentExecution = {
  id: string;
  task_id: string;
  stage: string;
  agent_type: string;
  status: string;
  output_result?: string;
  explanation?: string;
  error_message?: string;
  execution_time_ms?: number;
  created_at: string;
  task_description?: string;
  project_name?: string;
};

export function AgentStatusPanel({ userId }: { userId: string }) {
  const [executions, setExecutions] = useState<AgentExecution[]>([]);
  const [loading, setLoading] = useState(true);
  const [expandedId, setExpandedId] = useState<string | null>(null);

  useEffect(() => {
    const fetchExecutions = async () => {
      if (typeof document !== "undefined" && document.visibilityState !== "visible") {
        return;
      }
      try {
        const res = await fetch(`http://localhost:8000/api/agent/executions/${userId}`);
        if (res.ok) {
          const data = await res.json();
          setExecutions(data.executions || []);
        }
      } catch (e) {
        console.error("Failed to fetch agent executions:", e);
      } finally {
        setLoading(false);
      }
    };

    fetchExecutions();
    const interval = setInterval(fetchExecutions, 15000);
    return () => clearInterval(interval);
  }, [userId]);

  const statusColor = (status: string) => {
    switch (status) {
      case "success": return "text-green-400 bg-green-400/10 border-green-400/20";
      case "failed": return "text-red-400 bg-red-400/10 border-red-400/20";
      case "running": return "text-yellow-400 bg-yellow-400/10 border-yellow-400/20";
      default: return "text-gray-400 bg-gray-400/10 border-gray-400/20";
    }
  };

  const stageEmoji = (stage: string) => {
    switch (stage) {
      case "refine": return "🧠";
      case "dispatch": return "📤";
      case "execute": return "⚡";
      case "terminal": return "🖥️";
      case "complete": return "✅";
      default: return "🔷";
    }
  };

  if (loading) {
    return (
      <Card className="bg-dark-card border-dark-border p-6">
        <div className="flex items-center gap-2 mb-4">
          <div className="w-2 h-2 rounded-full bg-yellow-500 animate-pulse" />
          <h3 className="text-sm font-mono text-gray-400 uppercase tracking-wider">Agent Pipeline</h3>
        </div>
        <div className="space-y-3">
          {[1, 2, 3].map((i) => (
            <Skeleton key={i} className="h-16 bg-gray-800/50 rounded-lg" />
          ))}
        </div>
      </Card>
    );
  }

  if (executions.length === 0) {
    return (
      <Card className="bg-dark-card border-dark-border p-6">
        <div className="flex items-center gap-2 mb-4">
          <div className="w-2 h-2 rounded-full bg-gray-600" />
          <h3 className="text-sm font-mono text-gray-400 uppercase tracking-wider">Agent Pipeline</h3>
        </div>
        <p className="text-gray-600 text-sm font-mono text-center py-8">
          No agent executions yet. Record a voice command to dispatch tasks.
        </p>
      </Card>
    );
  }

  return (
    <Card className="bg-dark-card border-dark-border p-6">
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <div className="w-2 h-2 rounded-full bg-supabase-green animate-pulse" />
          <h3 className="text-sm font-mono text-gray-400 uppercase tracking-wider">Agent Pipeline</h3>
        </div>
        <span className="text-xs font-mono text-gray-600">{executions.length} executions</span>
      </div>

      <div className="space-y-2 max-h-96 overflow-y-auto pr-1">
        {executions.map((exec, i) => (
          <div
            key={exec.id}
            className={`
              rounded-lg border p-3 cursor-pointer transition-all duration-200
              hover:bg-white/[0.02] animate-fade-in-up
              ${statusColor(exec.status)}
            `}
            style={{ animationDelay: `${i * 0.05}s` }}
            onClick={() => setExpandedId(expandedId === exec.id ? null : exec.id)}
          >
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2 min-w-0">
                <span className="text-sm">{stageEmoji(exec.stage)}</span>
                <span className="text-sm font-medium text-gray-300 truncate">
                  {exec.task_description || exec.task_id.slice(0, 8)}
                </span>
                <Badge variant="outline" className="text-xs font-mono bg-black/30 text-gray-500 border-gray-700 px-1.5 py-0.5">
                  {exec.stage}
                </Badge>
              </div>
              <div className="flex items-center gap-2 shrink-0">
                {exec.execution_time_ms !== undefined && exec.execution_time_ms !== null && (
                  <span className="text-xs font-mono text-gray-600">{exec.execution_time_ms}ms</span>
                )}
                <Badge
                  variant="outline"
                  className={`text-xs font-mono font-bold border-0 px-0 ${
                    exec.status === "success" ? "text-green-400" :
                    exec.status === "failed" ? "text-red-400" :
                    exec.status === "running" ? "text-yellow-400" : "text-gray-500"
                  }`}
                >
                  {exec.status === "running" && "⏳ "}
                  {exec.status.toUpperCase()}
                </Badge>
              </div>
            </div>

            {/* Project name */}
            {exec.project_name && (
              <p className="text-xs font-mono text-gray-600 mt-1">
                📁 {exec.project_name}
              </p>
            )}

            {/* Expanded details */}
            {expandedId === exec.id && (
              <div className="mt-3 pt-3 border-t border-white/5 space-y-2 animate-fade-in-up">
                {exec.output_result && (
                  <div>
                    <p className="text-xs text-gray-500 mb-1">Output:</p>
                    <pre className="text-xs font-mono text-gray-400 bg-black/30 p-2 rounded overflow-x-auto max-h-40 whitespace-pre-wrap">
                      {exec.output_result}
                    </pre>
                  </div>
                )}
                {exec.explanation && (
                  <div>
                    <p className="text-xs text-gray-500 mb-1">Explanation:</p>
                    <p className="text-xs text-gray-400">{exec.explanation}</p>
                  </div>
                )}
                {exec.error_message && (
                  <div>
                    <p className="text-xs text-red-500 mb-1">Error:</p>
                    <p className="text-xs font-mono text-red-400/80">{exec.error_message}</p>
                  </div>
                )}
                <p className="text-xs text-gray-700 font-mono">
                  ID: {exec.id} • {new Date(exec.created_at).toLocaleString()}
                </p>
              </div>
            )}
          </div>
        ))}
      </div>
    </Card>
  );
}
