"use client";

import { useState } from "react";
import { authFetch } from "@/lib/supabase/access-token";
import { Card, CardHeader, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from "@/components/ui/dialog";

type DeleteHistoryResult = Record<string, number>;

function getErrorMessage(err: unknown, fallback: string): string {
  if (err instanceof Error && err.message) return err.message;
  return fallback;
}

export function SettingsDangerZone() {
  const backendUrl = process.env.NEXT_PUBLIC_BACKEND_URL ?? "http://localhost:8000";
  const [loading, setLoading] = useState(false);
  const [confirm, setConfirm] = useState(false);
  const [result, setResult] = useState<DeleteHistoryResult | null>(null);
  const [err, setErr] = useState<string | null>(null);

  const deleteHistory = async () => {
    setLoading(true);
    setErr(null);
    setResult(null);
    try {
      const res = await authFetch(`${backendUrl}/api/settings/history`, { method: "DELETE" });
      const data = await res.json();
      if (!res.ok) throw new Error(data?.detail ?? "Failed to delete history");
      setResult(data.deleted ?? {});
      setConfirm(false);
    } catch (e: unknown) {
      setErr(getErrorMessage(e, "Failed to delete history"));
    } finally {
      setLoading(false);
    }
  };

  return (
    <>
      <Card className="bg-dark-card border-red-500/20 overflow-hidden">
        <CardHeader className="bg-black/40 px-4 py-2 border-b border-white/5 space-y-0 pb-2">
          <span className="text-xs font-mono text-red-300/70">DANGER ZONE</span>
        </CardHeader>

        <CardContent className="p-6 space-y-3">
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
            <Button
              variant="destructive"
              onClick={() => setConfirm(true)}
              className="bg-red-500/15 hover:bg-red-500/25 border border-red-500/20 text-red-200"
            >
              Delete my history…
            </Button>
          </div>
        </CardContent>
      </Card>

      {/* Confirmation Dialog */}
      <Dialog open={confirm} onOpenChange={setConfirm}>
        <DialogContent className="bg-dark-card border-dark-border">
          <DialogHeader>
            <DialogTitle className="text-white">Delete all history?</DialogTitle>
            <DialogDescription className="text-gray-400">
              This will permanently delete call sessions, tasks, agent executions, terminal sessions, commands, logs, and local instance records. This action cannot be undone.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter className="gap-3 sm:gap-3">
            <Button
              variant="outline"
              onClick={() => setConfirm(false)}
              disabled={loading}
              className="text-gray-300 bg-white/5 border-white/10 hover:bg-white/10"
            >
              Cancel
            </Button>
            <Button
              variant="destructive"
              onClick={deleteHistory}
              disabled={loading}
            >
              {loading ? "Deleting…" : "Yes, delete"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}
