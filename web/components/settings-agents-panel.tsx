"use client";

import { useEffect, useMemo, useState } from "react";
import { getAuthHeader } from "@/lib/supabase/access-token";

type AgentTokenRow = {
  id: string;
  label?: string | null;
  created_at: string;
  last_used_at?: string | null;
  revoked_at?: string | null;
};

export function SettingsAgentsPanel() {
  const backendUrl = process.env.NEXT_PUBLIC_BACKEND_URL ?? "http://localhost:8000";
  const [tokens, setTokens] = useState<AgentTokenRow[]>([]);
  const [createdToken, setCreatedToken] = useState<string | null>(null);
  const [label, setLabel] = useState("");
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const installCommand = useMemo(() => {
    if (!createdToken) return null;
    return `python3 local-agent/dispatch_local_agent.py --backend-url "${backendUrl}" --project-path "/absolute/path/to/project" --agent-token "${createdToken}"`;
  }, [createdToken, backendUrl]);

  const loadTokens = async () => {
    setErr(null);
    try {
      const auth = await getAuthHeader();
      if (!auth) throw new Error("No auth token (please sign in again)");
      const res = await fetch(`${backendUrl}/api/settings/agent-tokens`, { headers: { ...auth }, cache: "no-store" });
      const data = await res.json();
      if (!res.ok) throw new Error(data?.detail ?? "Failed to load agent tokens");
      setTokens((data.tokens ?? []) as AgentTokenRow[]);
    } catch (e: any) {
      setErr(e?.message ?? "Failed to load agent tokens");
    }
  };

  useEffect(() => {
    loadTokens();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const createToken = async () => {
    setLoading(true);
    setErr(null);
    try {
      const auth = await getAuthHeader();
      if (!auth) throw new Error("No auth token (please sign in again)");
      const res = await fetch(`${backendUrl}/api/settings/agent-tokens`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...auth },
        body: JSON.stringify({ label: label.trim() || null }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data?.detail ?? "Failed to create token");
      setCreatedToken(String(data.token));
      setLabel("");
      await loadTokens();
    } catch (e: any) {
      setErr(e?.message ?? "Failed to create token");
    } finally {
      setLoading(false);
    }
  };

  const revokeToken = async (id: string) => {
    setLoading(true);
    setErr(null);
    try {
      const auth = await getAuthHeader();
      if (!auth) throw new Error("No auth token (please sign in again)");
      const res = await fetch(`${backendUrl}/api/settings/agent-tokens/${id}`, { method: "DELETE", headers: { ...auth } });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data?.detail ?? "Failed to revoke token");
      await loadTokens();
    } catch (e: any) {
      setErr(e?.message ?? "Failed to revoke token");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="bg-dark-card border border-dark-border rounded-xl overflow-hidden">
      <div className="bg-black/40 px-4 py-2 border-b border-white/5">
        <span className="text-xs font-mono text-gray-500">AGENTS</span>
      </div>

      <div className="p-6 space-y-4">
        <div>
          <h2 className="text-lg font-semibold text-white">Connect a local agent</h2>
          <p className="text-sm text-gray-400 mt-1">
            Create an agent token, then run the one-line command locally. Tokens can be revoked anytime.
          </p>
        </div>

        {err && <div className="text-xs font-mono text-red-400">{err}</div>}

        <div className="flex gap-2">
          <input
            value={label}
            onChange={(e) => setLabel(e.target.value)}
            placeholder="Label (optional): e.g. MacBook Pro"
            className="flex-1 text-sm bg-dark-bg border border-dark-border rounded-md px-3 py-2 text-white placeholder-gray-600 focus:outline-none focus:border-supabase-green"
          />
          <button
            onClick={createToken}
            disabled={loading}
            className="px-4 py-2 rounded-md bg-supabase-green text-black font-medium hover:bg-supabase-green-dark disabled:opacity-50"
          >
            Create token
          </button>
        </div>

        {createdToken && (
          <div className="bg-black/30 border border-white/10 rounded-lg p-4 space-y-2">
            <div className="flex items-center justify-between gap-3">
              <p className="text-xs font-mono text-gray-500">Your new agent token (shown once)</p>
              <button
                onClick={() => navigator.clipboard.writeText(createdToken)}
                className="text-xs font-mono px-2 py-1 rounded bg-white/5 hover:bg-white/10 border border-white/10 text-gray-300"
              >
                Copy
              </button>
            </div>
            <pre className="text-xs font-mono text-gray-200 whitespace-pre-wrap break-words">
              {createdToken}
            </pre>

            {installCommand && (
              <>
                <p className="text-xs font-mono text-gray-500 mt-3">Run this locally</p>
                <div className="flex items-start gap-2">
                  <pre className="flex-1 text-xs font-mono text-gray-200 whitespace-pre-wrap break-words bg-black/40 border border-white/10 rounded p-3">
                    {installCommand}
                  </pre>
                  <button
                    onClick={() => navigator.clipboard.writeText(installCommand)}
                    className="text-xs font-mono px-2 py-1 rounded bg-white/5 hover:bg-white/10 border border-white/10 text-gray-300"
                  >
                    Copy
                  </button>
                </div>
              </>
            )}
          </div>
        )}

        <div className="pt-2">
          <p className="text-xs font-mono text-gray-500 mb-2">Existing tokens</p>
          <div className="space-y-2">
            {tokens.map((t) => {
              const revoked = Boolean(t.revoked_at);
              return (
                <div
                  key={t.id}
                  className={`border rounded-lg p-3 ${revoked ? "border-white/5 bg-black/10" : "border-white/10 bg-black/20"}`}
                >
                  <div className="flex items-center justify-between gap-3">
                    <div className="min-w-0">
                      <div className="text-sm text-gray-200 truncate">
                        {t.label || "Unnamed token"}
                      </div>
                      <div className="text-[11px] font-mono text-gray-600">
                        created {new Date(t.created_at).toLocaleString()}
                        {t.last_used_at ? ` • last used ${new Date(t.last_used_at).toLocaleString()}` : ""}
                        {revoked ? ` • revoked ${new Date(t.revoked_at as string).toLocaleString()}` : ""}
                      </div>
                    </div>
                    <button
                      onClick={() => revokeToken(t.id)}
                      disabled={loading || revoked}
                      className="text-xs font-mono px-2 py-1 rounded bg-red-500/10 hover:bg-red-500/20 border border-red-500/20 text-red-300 disabled:opacity-50"
                    >
                      Revoke
                    </button>
                  </div>
                  <div className="text-[11px] font-mono text-gray-700 mt-2">
                    Token ID: {t.id}
                  </div>
                </div>
              );
            })}
            {tokens.length === 0 && (
              <div className="text-xs font-mono text-gray-600 bg-black/20 border border-white/10 rounded p-3">
                No tokens yet.
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

