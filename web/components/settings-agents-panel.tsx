"use client";

import { useEffect, useState } from "react";
import { authFetch } from "@/lib/supabase/access-token";

type CompanionDeviceRow = {
  id: string;
  name?: string | null;
  platform?: string | null;
  status: string;
  last_heartbeat?: string | null;
  created_at: string;
};

type DeviceProjectLinkRow = {
  id: string;
  device_id: string;
  project_id: string;
  project_name?: string | null;
  local_path?: string | null;
  created_at: string;
};

function getErrorMessage(err: unknown, fallback: string): string {
  if (err instanceof Error && err.message) return err.message;
  return fallback;
}

export function SettingsAgentsPanel() {
  const backendUrl = process.env.NEXT_PUBLIC_BACKEND_URL ?? "http://localhost:8000";
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [pairingCode, setPairingCode] = useState<string | null>(null);
  const [devices, setDevices] = useState<CompanionDeviceRow[]>([]);
  const [deviceProjects, setDeviceProjects] = useState<Record<string, DeviceProjectLinkRow[]>>({});
  const [loadingProjectsFor, setLoadingProjectsFor] = useState<string | null>(null);
  const [projectBasePath, setProjectBasePath] = useState<string>("");
  const [savingBasePath, setSavingBasePath] = useState(false);

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

  const loadProjectBasePath = async () => {
    setErr(null);
    try {
      const res = await authFetch(`${backendUrl}/api/settings/project-base-path`, { cache: "no-store" });
      const data = await res.json();
      if (!res.ok) throw new Error(data?.detail ?? "Failed to load project base path");
      setProjectBasePath(String(data?.base_path ?? ""));
    } catch (e: unknown) {
      setErr(getErrorMessage(e, "Failed to load project base path"));
    }
  };

  const loadDeviceProjects = async (deviceId: string) => {
    setLoadingProjectsFor(deviceId);
    setErr(null);
    try {
      const res = await authFetch(`${backendUrl}/api/device/${deviceId}/projects`, { cache: "no-store" });
      const data = await res.json();
      if (!res.ok) throw new Error(data?.detail ?? "Failed to load project links");
      setDeviceProjects((prev) => ({
        ...prev,
        [deviceId]: (data.links ?? []) as DeviceProjectLinkRow[],
      }));
    } catch (e: unknown) {
      setErr(getErrorMessage(e, "Failed to load project links"));
    } finally {
      setLoadingProjectsFor(null);
    }
  };

  const saveDeviceProjectLocalPath = async (deviceId: string, projectId: string, nextLocalPath: string) => {
    setLoadingProjectsFor(`${deviceId}:${projectId}`);
    setErr(null);
    try {
      const res = await authFetch(`${backendUrl}/api/device/${deviceId}/projects`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ project_id: projectId, local_path: nextLocalPath }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data?.detail ?? "Failed to update local_path");
      await loadDeviceProjects(deviceId);
    } catch (e: unknown) {
      setErr(getErrorMessage(e, "Failed to update local_path"));
    } finally {
      setLoadingProjectsFor(null);
    }
  };

  useEffect(() => {
    loadDevices();
    loadProjectBasePath();
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

  return (
    <div className="bg-dark-card border border-dark-border rounded-xl overflow-hidden">
      <div className="bg-black/40 px-4 py-2 border-b border-white/5">
        <span className="text-xs font-mono text-gray-500">AGENTS</span>
      </div>

      <div className="p-6 space-y-4">
        <div>
          <h2 className="text-lg font-semibold text-white">Desktop Companion pairing</h2>
          <p className="text-sm text-gray-400 mt-1">
            Click “Create pairing code”, then open the desktop companion app to pair and choose project folders.
          </p>
        </div>

        <div className="bg-black/20 border border-white/10 rounded-lg p-4 space-y-3">
          <div>
            <div className="text-xs font-mono text-gray-500">New Projects Location</div>
            <div className="text-sm text-gray-300 mt-1">
              When you create a new project, the app will place it under this absolute directory on your computer.
            </div>
          </div>
          <div className="flex gap-2">
            <input
              value={projectBasePath}
              onChange={(e) => setProjectBasePath(e.target.value)}
              placeholder="/absolute/path/to/projects"
              className="flex-1 text-sm bg-dark-bg border border-dark-border rounded-md px-3 py-2 text-white placeholder-gray-600 focus:outline-none focus:border-supabase-green"
            />
            <button
              onClick={async () => {
                setSavingBasePath(true);
                setErr(null);
                try {
                  const next = projectBasePath.trim() || null;
                  const res = await authFetch(`${backendUrl}/api/settings/project-base-path`, {
                    method: "PUT",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ base_path: next }),
                  });
                  const data = await res.json().catch(() => ({}));
                  if (!res.ok) throw new Error(data?.detail ?? "Failed to save base path");
                  setProjectBasePath(String(data?.base_path ?? ""));
                } catch (e: unknown) {
                  setErr(getErrorMessage(e, "Failed to save base path"));
                } finally {
                  setSavingBasePath(false);
                }
              }}
              disabled={savingBasePath}
              className="px-4 py-2 rounded-md bg-supabase-green text-black font-medium hover:bg-supabase-green-dark disabled:opacity-50"
            >
              {savingBasePath ? "Saving..." : "Save"}
            </button>
          </div>
          <div className="text-[11px] text-gray-500">
            This can be set once. Folder creation happens on the desktop companion when it needs to run commands.
          </div>
        </div>

        {err && <div className="text-xs font-mono text-red-400">{err}</div>}

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
            Recommended: use the desktop GUI (`companion npm run gui`) to pick your project folder with an OS directory
            picker. This writes the correct <span className="font-mono">local_path</span> so commands execute in the right place.
          </p>
          <p className="text-[11px] text-gray-500">
            After pairing, open your desktop companion app and click “Link missing projects”.
          </p>
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

                <div className="pt-3">
                  <div className="flex items-center justify-between gap-3">
                    <div className="text-xs font-mono text-gray-500">Project local paths</div>
                    <button
                      onClick={() => loadDeviceProjects(d.id)}
                      disabled={loadingProjectsFor === d.id}
                      className="text-xs font-mono px-2 py-1 rounded bg-white/5 hover:bg-white/10 border border-white/10 text-gray-300 disabled:opacity-50"
                    >
                      {loadingProjectsFor === d.id ? "Loading..." : "Refresh"}
                    </button>
                  </div>
                  {(deviceProjects[d.id]?.length ?? 0) > 0 ? (
                    <div className="mt-2 space-y-2">
                      {deviceProjects[d.id].map((p) => (
                        <div key={p.id} className="bg-black/20 border border-white/10 rounded p-2">
                          <div className="text-[11px] font-mono text-gray-200">
                            {p.project_name || p.project_id}
                          </div>
                          <div className="mt-1 flex gap-2 items-start">
                            <input
                              className="flex-1 text-[11px] font-mono bg-dark-bg border border-dark-border rounded-md px-2 py-2 text-white"
                              value={p.local_path || ""}
                              placeholder="Paste absolute local_path (folder) for this device"
                              onChange={(e) => {
                                const next = e.target.value;
                                setDeviceProjects((prev) => ({
                                  ...prev,
                                  [d.id]: (prev[d.id] ?? []).map((row) =>
                                    row.id === p.id ? { ...row, local_path: next } : row
                                  ),
                                }));
                              }}
                            />
                            <button
                              onClick={() => saveDeviceProjectLocalPath(d.id, p.project_id, p.local_path || "")}
                              disabled={loadingProjectsFor === `${d.id}:${p.project_id}`}
                              className="text-[11px] font-mono px-2 py-2 rounded bg-supabase-green text-black hover:bg-supabase-green-dark disabled:opacity-50"
                            >
                              Save
                            </button>
                          </div>
                          {!p.local_path ? (
                            <div className="text-[11px] font-mono text-red-300 mt-1">
                              Missing local_path: companion will currently run in the wrong directory.
                            </div>
                          ) : null}
                        </div>
                      ))}
                    </div>
                  ) : (
                    <div className="text-xs font-mono text-gray-500 mt-2">
                      Click <span className="font-mono">Refresh</span> to load linked projects and local paths.
                    </div>
                  )}
                </div>
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

