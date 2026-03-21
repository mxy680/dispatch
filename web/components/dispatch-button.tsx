"use client";
import { useState } from "react";
import { authFetch } from "@/lib/supabase/access-token";

export function DispatchButton({ taskId }: { taskId: string }) {
  const backendUrl = process.env.NEXT_PUBLIC_BACKEND_URL ?? "http://localhost:8000";
  const [dispatching, setDispatching] = useState(false);
  const [result, setResult] = useState<string | null>(null);

  const handleDispatch = async () => {
    setDispatching(true);
    setResult(null);
    try {
      const res = await authFetch(`${backendUrl}/api/agent/dispatch/${taskId}`, { method: "POST" });
      const data = await res.json();
      if (data.success) {
        setResult("✓ Dispatched");
      } else {
        setResult("✗ Failed");
      }
    } catch {
      setResult("✗ Error");
    } finally {
      setDispatching(false);
      setTimeout(() => setResult(null), 3000);
    }
  };

  return (
    <div className="inline-flex items-center gap-2">
      <button
        onClick={handleDispatch}
        disabled={dispatching}
        className={`
          text-xs px-2 py-1 rounded font-mono transition-all duration-200
          ${dispatching
            ? "bg-yellow-500/20 text-yellow-400 cursor-wait"
            : "bg-supabase-green/10 text-supabase-green hover:bg-supabase-green/20 border border-supabase-green/20"
          }
        `}
      >
        {dispatching ? (
          <span className="flex items-center gap-1">
            <div className="w-3 h-3 border-2 border-yellow-400 border-t-transparent rounded-full animate-spin" />
            Dispatching...
          </span>
        ) : (
          "⚡ Dispatch to Agent"
        )}
      </button>
      {result && (
        <span className={`text-xs font-mono animate-fade-in-up ${
          result.startsWith("✓") ? "text-green-400" : "text-red-400"
        }`}>
          {result}
        </span>
      )}
    </div>
  );
}
