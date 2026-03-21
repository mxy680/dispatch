"use client";
import { useState } from "react";
import { Button } from "@/components/ui/button";
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
      <Button
        variant="outline"
        size="sm"
        onClick={handleDispatch}
        disabled={dispatching}
        className={`
          text-xs font-mono transition-all duration-200
          ${dispatching
            ? "bg-yellow-500/20 text-yellow-400 border-yellow-500/20 cursor-wait hover:bg-yellow-500/20 hover:text-yellow-400"
            : "bg-supabase-green/10 text-supabase-green border-supabase-green/20 hover:bg-supabase-green/20"
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
      </Button>
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
