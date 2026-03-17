"use client";

import { useState } from "react";
import { getAuthHeader } from "@/lib/supabase/access-token";

export function SettingsDangerZone() {
  const backendUrl = process.env.NEXT_PUBLIC_BACKEND_URL ?? "http://localhost:8000";
  const [loading, setLoading] = useState(false);
  const [confirm, setConfirm] = useState(false);
  const [result, setResult] = useState<any | null>(null);
  const [err, setErr] = useState<string | null>(null);

  const deleteHistory = async () => {
    setLoading(true);
    setErr(null);
    setResult(null);
    try {
      const auth = await getAuthHeader();
      if (!auth) throw new Error("No auth token (please sign in again)");
      const res = await fetch(`${backendUrl}/api/settings/history`, { method: "DELETE", headers: { ...auth } });
      const data = await res.json();
      if (!res.ok) throw new Error(data?.detail ?? "Failed to delete history");
      setResult(data.deleted ?? {});
      setConfirm(false);
    } catch (e: any) {
      setErr(e?.message ?? "Failed to delete history");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="bg-dark-card border border-red-500/20 rounded-xl overflow-hidden">
      <div className="bg-black/40 px-4 py-2 border-b border-white/5">
        <span className="text-xs font-mono text-red-300/70">DANGER ZONE</span>
      </div>

      <div className="p-6 space-y-3">
        <div>
          <h2 className="text-lg font-semibold text-white">Delete history</h2>
          <p className="text-sm text-gray-400 mt-1">
            Deletes call sessions, tasks, agent executions, terminal sessions/commands/logs, and local instance records from this app.
          </p>
        </div>

        {err && <div className="text-xs font-mono text-red-400">{err}</div>}

        {result && (
          <div className="bg-black/30 border border-white/10 rounded-lg p-4">
            <p className="text-xs font-mono text-gray-500 mb-2">Deleted rows</p>
            <pre className="text-xs font-mono text-gray-200 whitespace-pre-wrap">
              {JSON.stringify(result, null, 2)}
            </pre>
          </div>
        )}

        <div className="flex items-center gap-3">
          {!confirm ? (
            <button
              onClick={() => setConfirm(true)}
              className="px-4 py-2 rounded-md bg-red-500/15 hover:bg-red-500/25 border border-red-500/20 text-red-200 font-medium"
            >
              Delete my history…
            </button>
          ) : (
            <>
              <button
                onClick={deleteHistory}
                disabled={loading}
                className="px-4 py-2 rounded-md bg-red-500 text-white font-semibold hover:bg-red-600 disabled:opacity-50"
              >
                {loading ? "Deleting…" : "Yes, delete"}
              </button>
              <button
                onClick={() => setConfirm(false)}
                disabled={loading}
                className="px-4 py-2 rounded-md bg-white/5 hover:bg-white/10 border border-white/10 text-gray-300 disabled:opacity-50"
              >
                Cancel
              </button>
            </>
          )}
        </div>
      </div>
    </div>
  );
}

