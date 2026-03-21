import { DashboardPoller } from "@/components/dashboard-poller";
import { createClient } from "@/lib/supabase/server";
import { redirect } from "next/navigation";
import { VoiceRecorder } from "@/components/voice-recorder";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { TerminalAccessToggle } from "@/components/terminal-access-toggle";
import { UnifiedCommandCenter } from "@/components/unified-command-center";
import Link from "next/link";

type ProjectRow = {
  id: string;
  name: string;
  status: string | null;
  total_tasks: number | null;
  pending_tasks: number | null;
  in_progress_tasks: number | null;
  completed_tasks: number | null;
};

type TaskRow = {
  id: string;
  project_id: string;
  project_name?: string | null;
  description: string;
  status: string;
  created_at: string;
  intent_type?: string | null;
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

export default async function DashboardPage() {
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();

  if (!user) redirect("/login");
  const {
    data: { session },
  } = await supabase.auth.getSession();

  const backendUrl = process.env.BACKEND_URL ?? process.env.NEXT_PUBLIC_BACKEND_URL ?? "http://localhost:8000";
  const dashRes = await fetch(`${backendUrl}/api/dashboard/${user.id}`, {
    cache: "no-store",
    headers: session?.access_token ? { Authorization: `Bearer ${session.access_token}` } : undefined,
  });
  const dashJson = (await dashRes.json()) as { projects: ProjectRow[]; tasks: TaskRow[] };

  const projects = dashJson.projects ?? [];
  const tasks = dashJson.tasks ?? [];

  return (
    <div className="max-w-4xl mx-auto space-y-6">
      <DashboardPoller intervalMs={5000} />

      {/* ── Navigation ── */}
      <div className="flex items-center justify-between">
        <div className="space-y-1">
          <h1 className="text-3xl font-bold tracking-tight">Dispatch</h1>
          <p className="text-gray-400 text-sm">
            Connected as{" "}
            <span className="text-supabase-green font-mono">{user.phone || user.email}</span>
          </p>
        </div>
        <div className="flex items-center gap-3 text-sm">
          <Link href="/dashboard/history" className="text-gray-400 hover:text-white transition-colors">
            History
          </Link>
          <Link href="/dashboard/settings" className="text-gray-400 hover:text-white transition-colors">
            Settings
          </Link>
        </div>
      </div>

      {/* ── Terminal Access Toggle ── */}
      <TerminalAccessToggle userId={user.id} />

      {/* ── Unified Command Center ── */}
      <UnifiedCommandCenter projects={projects.map((p) => ({ id: p.id, name: p.name }))} />

      {/* ── Voice Command Input ── */}
      <VoiceRecorder />

      {/* ── Projects ── */}
      <Card>
        <CardHeader className="pb-2">
          <div className="flex items-center justify-between">
            <CardTitle className="text-sm font-medium">Projects</CardTitle>
            <span className="text-xs text-muted-foreground tabular-nums">{projects.length} total</span>
          </div>
        </CardHeader>
        <CardContent className="p-0">
          {projects.length === 0 ? (
            <p className="px-6 py-8 text-sm text-muted-foreground text-center">
              No projects yet. Try: &quot;Create a project called my-api&quot;
            </p>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Name</TableHead>
                  <TableHead className="text-right">Tasks</TableHead>
                  <TableHead className="text-right">Done</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {projects.map((p) => (
                  <TableRow key={p.id}>
                    <TableCell className="font-medium">{p.name}</TableCell>
                    <TableCell className="text-right tabular-nums">{p.total_tasks ?? 0}</TableCell>
                    <TableCell className="text-right tabular-nums text-emerald-400">{p.completed_tasks ?? 0}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>

      {/* ── Recent Tasks ── */}
      <Card>
        <CardHeader className="pb-2">
          <div className="flex items-center justify-between">
            <CardTitle className="text-sm font-medium">Recent Tasks</CardTitle>
            <span className="text-xs text-muted-foreground tabular-nums">{tasks.length} total</span>
          </div>
        </CardHeader>
        <CardContent className="p-0">
          {tasks.length === 0 ? (
            <p className="px-6 py-8 text-sm text-muted-foreground text-center">
              No tasks yet. Use the command input above to create one.
            </p>
          ) : (
            <div className="divide-y divide-border">
              {tasks.slice(0, 20).map((t) => (
                <div key={t.id} className="px-6 py-3 flex items-start gap-3">
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium truncate">{t.description}</p>
                    <p className="text-xs text-muted-foreground mt-0.5">
                      {t.project_name ?? "Unknown project"}
                    </p>
                  </div>
                  <div className="flex items-center gap-2 shrink-0">
                    <Badge variant="outline" className={`text-[10px] border ${statusBadge(t.status)}`}>
                      {t.status}
                    </Badge>
                    <span className="text-[10px] text-muted-foreground whitespace-nowrap">
                      {timeAgo(t.created_at)}
                    </span>
                  </div>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
