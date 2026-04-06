"use client";

import { useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { CommandLogViewer } from "@/components/command-log-viewer";

type ActivityItem = {
  id: string;
  label: string;
  project: string | null;
  status: string;
  time: string;
  type: "task" | "command";
};

function statusBadge(status: string) {
  const styles: Record<string, string> = {
    completed: "bg-emerald-500/15 text-emerald-400 border-emerald-500/20",
    agent_completed: "bg-emerald-500/15 text-emerald-400 border-emerald-500/20",
    in_progress: "bg-blue-500/15 text-blue-400 border-blue-500/20",
    pending: "bg-amber-500/15 text-amber-400 border-amber-500/20",
  };
  return styles[status] ?? "bg-muted text-muted-foreground";
}

function timeAgo(iso: string) {
  const seconds = Math.floor((Date.now() - new Date(iso).getTime()) / 1000);
  if (seconds < 60) return "just now";
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`;
  if (seconds < 86400) return `${Math.floor(seconds / 3600)}h ago`;
  return `${Math.floor(seconds / 86400)}d ago`;
}

export function RecentActivityCard({ activity }: { activity: ActivityItem[] }) {
  const [selectedCommandId, setSelectedCommandId] = useState<string | null>(null);

  const selectedItem = activity.find((a) => a.id === selectedCommandId) ?? null;

  function handleCommandClick(id: string) {
    setSelectedCommandId((prev) => (prev === id ? null : id));
  }

  return (
    <Card>
      <CardHeader className="pb-2">
        <div className="flex items-center justify-between">
          <CardTitle className="text-sm font-medium">Recent Activity</CardTitle>
          <span className="text-xs text-muted-foreground tabular-nums">{activity.length}</span>
        </div>
      </CardHeader>
      <CardContent className="p-0">
        {activity.length === 0 ? (
          <p className="px-6 py-8 text-sm text-muted-foreground text-center">
            No activity yet. Send a command above.
          </p>
        ) : (
          <>
            <div className="divide-y divide-border max-h-[300px] overflow-auto">
              {activity.map((a) => {
                const isClickable = a.type === "command";
                const isSelected = a.id === selectedCommandId;

                return (
                  <div
                    key={a.id}
                    onClick={isClickable ? () => handleCommandClick(a.id) : undefined}
                    className={`px-4 py-2.5 flex items-start gap-3 transition-colors ${
                      isClickable
                        ? isSelected
                          ? "bg-accent cursor-pointer"
                          : "cursor-pointer hover:bg-accent/50"
                        : ""
                    }`}
                  >
                    <div className="flex-1 min-w-0">
                      <p className="text-sm truncate">{a.label}</p>
                      <p className="text-xs text-muted-foreground mt-0.5">
                        {a.project ?? "Unknown project"}
                      </p>
                    </div>
                    <div className="flex items-center gap-2 shrink-0">
                      <Badge variant="outline" className={`text-[10px] border ${statusBadge(a.status)}`}>
                        {a.status}
                      </Badge>
                      <span className="text-[10px] text-muted-foreground whitespace-nowrap" suppressHydrationWarning>
                        {timeAgo(a.time)}
                      </span>
                    </div>
                  </div>
                );
              })}
            </div>

            {selectedCommandId && selectedItem && (
              <div className="border-t border-border">
                <div className="flex items-center justify-between px-4 py-2">
                  <span className="text-xs text-muted-foreground truncate max-w-[80%]">
                    {selectedItem.label}
                  </span>
                  <Button
                    variant="ghost"
                    size="icon"
                    onClick={() => setSelectedCommandId(null)}
                    className="ml-2 shrink-0 h-6 w-6"
                    aria-label="Close log viewer"
                  >
                    ✕
                  </Button>
                </div>
                <CommandLogViewer
                  commandId={selectedCommandId}
                  commandStatus={selectedItem.status}
                />
              </div>
            )}
          </>
        )}
      </CardContent>
    </Card>
  );
}
