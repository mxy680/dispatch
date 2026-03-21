"use client";

import { useEffect, useMemo, useState } from "react";
import { authFetch } from "@/lib/supabase/access-token";

type AgentTokenRow = {
  id: string;
  label?: string | null;
  created_at: string;
  last_used_at?: string | null;
  revoked_at?: string | null;
};

type CompanionDeviceRow = {
  id: string;
  name?: string | null;
  platform?: string | null;
  status: string;
  last_heartbeat?: string | null;
  created_at: string;
};

function getErrorMessage(err: unknown, fallback: string): string {
  if (err instanceof Error && err.message) return err.message;
  return fallback;
}

export function SettingsAgentsPanel() {
  const backendUrl = process.env.NEXT_PUBLIC_BACKEND_URL ?? "http://localhost:8000";
  const [tokens, setTokens] = useState<AgentTokenRow[]>([]);
  const [createdToken, setCreatedToken] = useState<string | null>(null);
  const [label, setLabel] = useState("");
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [pairingCode, setPairingCode] = useState<string | null>(null);
  const [devices, setDevices] = useState<CompanionDeviceRow[]>([]);

  const installCommand = useMemo(() => {
    if (!createdToken) return null;
    return `python3 local-agent/dispatch_local_agent.py --backend-url "${backendUrl}" --project-path "/absolute/path/to/project" --agent-token "${createdToken}"`;
  }, [createdToken, backendUrl]);

  const loadTokens = async () => {
    setErr(null);
    try {
      const res = await authFetch(`${backendUrl}/api/settings/agent-tokens`, { cache: "no-store" });
      const data = await res.json();
      if (!res.ok) throw new Error(data?.detail ?? "Failed to load agent tokens");
      setTokens((data.tokens ?? []) as AgentTokenRow[]);
    } catch (e: unknown) {
      setErr(getErrorMessage(e, "Failed to load agent tokens"));
    }
  };

  const loadDevices = async () => {
    try {
      const res = await authFetch(`${backendUrl}/api/device`, { cache: "no-store" });
      const data = await res.json();
      if (!res.ok) throw new Error(data?.detail ?? "Failed to load devices");
      setDevices((data.devices ?? []) as CompanionDeviceRow[]);
    } catch (e: unknown) {
      setErr(getErrorMessage(e, "Failed to load devices"));
    }
  };

  useEffect(() => {
    loadTokens();
    loadDevices();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const createPairingCode = async () => {
    setLoading(true);
    setErr(null);
    try {
      const res = await authFetch(`${backendUrl}/api/device/pair/start`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: "Dispatch Companion", platform: navigator.platform }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data?.detail ?? "Failed to create pairing code");
      setPairingCode(String(data.pairing_code));
      await loadDevices();
    } catch (e: unknown) {
      setErr(getErrorMessage(e, "Failed to create pairing code"));
    } finally {
      setLoading(false);
    }
  };

  const createToken = async () => {
    setLoading(true);
    setErr(null);
    try {
      const res = await authFetch(`${backendUrl}/api/settings/agent-tokens`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ label: label.trim() || null }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data?.detail ?? "Failed to create token");
      setCreatedToken(String(data.token));
      setLabel("");
      await loadTokens();
    } catch (e: unknown) {
      setErr(getErrorMessage(e, "Failed to create token"));
    } finally {
      setLoading(false);
    }
  };

  const revokeToken = async (id: string) => {
    setLoading(true);
    setErr(null);
    try {
      const res = await authFetch(`${backendUrl}/api/settings/agent-tokens/${id}`, { method: "DELETE" });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data?.detail ?? "Failed to revoke token");
      await loadTokens();
    } catch (e: unknown) {
      setErr(getErrorMessage(e, "Failed to revoke token"));
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

        <div className="bg-black/20 border border-white/10 rounded-lg p-4 space-y-2">
          <div className="flex items-center justify-between">
            <p className="text-xs font-mono text-gray-500">Desktop Companion Pairing</p>
            <button
              onClick={createPairingCode}
              disabled={loading}
              className="text-xs font-mono px-2 py-1 rounded bg-white/5 hover:bg-white/10 border border-white/10 text-gray-300 disabled:opacity-50"
            >
              Create pairing code
            </button>
          </div>
          {pairingCode ? (
            <div className="text-sm font-mono text-supabase-green">{pairingCode}</div>
          ) : (
            <p className="text-xs text-gray-400">
              Generate a short-lived pairing code and enter it in the companion app.
            </p>
          )}
          <p className="text-[11px] text-gray-500">
            Companion scaffold folder: <span className="font-mono">companion/</span>. Cursor extension scaffold:
            <span className="font-mono"> cursor-extension/</span>.
          </p>
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
                <div className="mt-3 bg-black/40 border border-white/10 rounded p-3">
                  <p className="text-xs font-mono text-gray-500 mb-2">Cursor integration (step-by-step)</p>
                  <ol className="text-xs text-gray-300 space-y-1 list-decimal list-inside">
                    <li>Install the agent on the same machine where Cursor is running.</li>
                    <li>Start the local helper using the command above.</li>
                    <li>In Cursor, open your project folder matching <span className="font-mono">--project-path</span>.</li>
                    <li>Install Cursor CLI or Claude CLI in that shell.</li>
                    <li>In Dashboard, choose the provider and send a typed or voice command.</li>
                    <li>Watch live command output in the Unified Command Center timeline.</li>
                  </ol>
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

        <div className="pt-2">
          <p className="text-xs font-mono text-gray-500 mb-2">Connected companion devices</p>
          <div className="space-y-2">
            {devices.map((d) => (
              <div key={d.id} className="border border-white/10 bg-black/20 rounded-lg p-3">
                <div className="text-sm text-gray-200">{d.name || "Unnamed device"}</div>
                <div className="text-[11px] font-mono text-gray-500">
                  {d.platform || "unknown"} • {d.status} • created {new Date(d.created_at).toLocaleString()}
                  {d.last_heartbeat ? ` • heartbeat ${new Date(d.last_heartbeat).toLocaleString()}` : ""}
                </div>
                <div className="text-[11px] font-mono text-gray-700 mt-1">Device ID: {d.id}</div>
              </div>
            ))}
            {devices.length === 0 && (
              <div className="text-xs font-mono text-gray-600 bg-black/20 border border-white/10 rounded p-3">
                No companion devices paired yet.
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

