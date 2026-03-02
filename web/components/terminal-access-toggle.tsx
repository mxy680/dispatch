"use client";
import { useState, useEffect } from "react";

export function TerminalAccessToggle({ userId }: { userId: string }) {
  const [granted, setGranted] = useState(false);
  const [loading, setLoading] = useState(true);
  const [showConfirm, setShowConfirm] = useState(false);
  const [animating, setAnimating] = useState(false);

  useEffect(() => {
    fetch(`http://localhost:8000/api/agent/terminal-access/${userId}`)
      .then((r) => r.json())
      .then((d) => setGranted(d.terminal_access ?? false))
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [userId]);

  const handleToggle = async () => {
    if (!granted) {
      // Show confirmation before granting
      setShowConfirm(true);
      return;
    }
    // Revoking — no confirmation needed
    await doRevoke();
  };

  const doGrant = async () => {
    setShowConfirm(false);
    setAnimating(true);
    try {
      const res = await fetch(`http://localhost:8000/api/agent/terminal-access/${userId}`, {
        method: "POST",
      });
      if (res.ok) setGranted(true);
    } catch {
      // silently fail
    } finally {
      setTimeout(() => setAnimating(false), 500);
    }
  };

  const doRevoke = async () => {
    setAnimating(true);
    try {
      const res = await fetch(`http://localhost:8000/api/agent/terminal-access/${userId}`, {
        method: "DELETE",
      });
      if (res.ok) setGranted(false);
    } catch {
      // silently fail
    } finally {
      setTimeout(() => setAnimating(false), 500);
    }
  };

  if (loading) {
    return (
      <div className="bg-dark-card border border-dark-border rounded-xl p-4">
        <div className="h-10 bg-gray-800/50 rounded animate-shimmer" />
      </div>
    );
  }

  return (
    <>
      <div
        className={`bg-dark-card border rounded-xl p-4 transition-all duration-300 ${
          granted ? "border-supabase-green/30 shadow-[0_0_15px_rgba(62,207,142,0.1)]" : "border-dark-border"
        } ${animating ? "scale-[1.01]" : ""}`}
      >
        <div className="flex items-center justify-between gap-4">
          <div className="flex items-center gap-3 min-w-0">
            {/* Terminal icon */}
            <div
              className={`w-10 h-10 rounded-lg flex items-center justify-center transition-all duration-300 ${
                granted
                  ? "bg-supabase-green/20 text-supabase-green"
                  : "bg-gray-800 text-gray-500"
              }`}
            >
              <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} className="w-5 h-5">
                <polyline points="4 17 10 11 4 5" />
                <line x1="12" y1="19" x2="20" y2="19" />
              </svg>
            </div>
            <div>
              <p className="text-sm font-medium text-gray-200">Terminal Auto-Execution</p>
              <p className="text-xs text-gray-500 font-mono">
                {granted
                  ? "Tasks will auto-execute in Terminal.app"
                  : "Tasks dispatched as files only"}
              </p>
            </div>
          </div>

          {/* Toggle switch */}
          <button
            onClick={handleToggle}
            className={`relative w-12 h-6 rounded-full transition-all duration-300 ${
              granted ? "bg-supabase-green" : "bg-gray-700"
            }`}
          >
            <div
              className={`absolute top-0.5 w-5 h-5 rounded-full bg-white shadow-md transition-all duration-300 ${
                granted ? "left-[26px]" : "left-0.5"
              }`}
            />
          </button>
        </div>

        {/* Status indicator */}
        {granted && (
          <div className="mt-3 flex items-center gap-2 animate-fade-in-up">
            <div className="w-1.5 h-1.5 rounded-full bg-supabase-green animate-pulse" />
            <p className="text-xs font-mono text-supabase-green/70">
              Terminal access active — scripts will auto-launch
            </p>
          </div>
        )}
      </div>

      {/* Confirmation Modal */}
      {showConfirm && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 animate-fade-in-up">
          <div className="bg-dark-card border border-dark-border rounded-xl p-6 max-w-md mx-4 shadow-2xl animate-stage-enter">
            {/* Warning icon */}
            <div className="w-12 h-12 mx-auto mb-4 rounded-full bg-yellow-500/10 flex items-center justify-center">
              <svg className="w-6 h-6 text-yellow-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v3.75m-9.303 3.376c-.866 1.5.217 3.374 1.948 3.374h14.71c1.73 0 2.813-1.874 1.948-3.374L13.949 3.378c-.866-1.5-3.032-1.5-3.898 0L2.697 16.126zM12 15.75h.007v.008H12v-.008z" />
              </svg>
            </div>

            <h3 className="text-lg font-bold text-center text-white mb-2">
              Grant Terminal Access?
            </h3>

            <div className="space-y-3 mb-6">
              <p className="text-sm text-gray-400 text-center">
                This allows CallStack to automatically execute scripts in your terminal.
              </p>

              <div className="bg-black/30 rounded-lg p-3 space-y-2">
                <p className="text-xs font-mono text-gray-500 uppercase tracking-wider">What this enables:</p>
                <ul className="text-xs text-gray-400 space-y-1">
                  <li className="flex items-center gap-2">
                    <span className="text-supabase-green">✓</span> Open VS Code on agent workspace automatically
                  </li>
                  <li className="flex items-center gap-2">
                    <span className="text-supabase-green">✓</span> Run GitHub Copilot CLI suggestions in terminal
                  </li>
                  <li className="flex items-center gap-2">
                    <span className="text-supabase-green">✓</span> Auto-generate and execute shell scripts
                  </li>
                  <li className="flex items-center gap-2">
                    <span className="text-supabase-green">✓</span> Write results back to the pipeline
                  </li>
                </ul>
              </div>

              <div className="bg-yellow-500/5 border border-yellow-500/10 rounded-lg p-3">
                <p className="text-xs text-yellow-400/80">
                  ⚠ Scripts run with your user permissions. Only grant this on trusted devices.
                  You can revoke access at any time.
                </p>
              </div>
            </div>

            <div className="flex gap-3">
              <button
                onClick={() => setShowConfirm(false)}
                className="flex-1 px-4 py-2 rounded-lg text-sm font-medium text-gray-400 bg-gray-800 hover:bg-gray-700 transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={doGrant}
                className="flex-1 px-4 py-2 rounded-lg text-sm font-medium text-black bg-supabase-green hover:bg-supabase-green-dark transition-colors"
              >
                Grant Access
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
