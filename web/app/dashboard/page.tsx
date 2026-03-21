import { DashboardPoller } from "@/components/dashboard-poller";
import { createClient } from "@/lib/supabase/server";
import { redirect } from "next/navigation";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
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
import { CreateProjectDialog } from "@/components/create-project-dialog";
import { DeleteProjectButton } from "@/components/delete-project-button";
import { RecentActivityCard } from "@/components/recent-activity-card";

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

  // Also fetch recent commands for the activity feed
  const cmdRes = await fetch(`${backendUrl}/api/unified/timeline?limit=20`, {
    cache: "no-store",
    headers: session?.access_token ? { Authorization: `Bearer ${session.access_token}` } : undefined,
  });
  const cmdJson = (await cmdRes.json()) as { commands?: { id: string; user_prompt?: string; command: string; status: string; provider?: string; project_name?: string; created_at: string }[] };
  const recentCommands = cmdJson.commands ?? [];

  // Merge tasks + commands into one activity feed, sorted by time
  const activity = [
    ...tasks.map((t) => ({ id: t.id, label: t.description, project: t.project_name, status: t.status, time: t.created_at, type: "task" as const })),
    ...recentCommands.map((c) => ({ id: c.id, label: c.user_prompt || c.command, project: c.project_name, status: c.status, time: c.created_at, type: "command" as const })),
  ].sort((a, b) => new Date(b.time).getTime() - new Date(a.time).getTime()).slice(0, 20);

  return (
    <div className="max-w-5xl mx-auto space-y-6">
      <DashboardPoller intervalMs={5000} />

      {/* Header */}
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold tracking-tight">Dashboard</h1>
        <TerminalAccessToggle userId={user.id} />
      </div>

      {/* Command Center */}
      <UnifiedCommandCenter projects={projects.map((p) => ({ id: p.id, name: p.name }))} />

      {/* Projects + Tasks side by side */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {/* Projects */}
        <Card>
          <CardHeader className="pb-2">
            <div className="flex items-center justify-between">
              <CardTitle className="text-sm font-medium">Projects</CardTitle>
              <CreateProjectDialog userId={user.id} />
            </div>
          </CardHeader>
          <CardContent className="p-0">
            {projects.length === 0 ? (
              <p className="px-6 py-8 text-sm text-muted-foreground text-center">
                No projects yet. Use agent mode to create one.
              </p>
            ) : (
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Name</TableHead>
                    <TableHead className="text-right w-16">Tasks</TableHead>
                    <TableHead className="text-right w-16">Done</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {projects.map((p) => (
                    <TableRow key={p.id}>
                      <TableCell className="font-medium text-sm">
                        <div className="flex items-center gap-2">
                          {p.name}
                          <DeleteProjectButton projectId={p.id} />
                        </div>
                      </TableCell>
                      <TableCell className="text-right tabular-nums text-sm">{p.total_tasks ?? 0}</TableCell>
                      <TableCell className="text-right tabular-nums text-sm text-emerald-400">{p.completed_tasks ?? 0}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            )}
          </CardContent>
        </Card>

        <RecentActivityCard activity={activity} />
      </div>
    </div>
  );
}
