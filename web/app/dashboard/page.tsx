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

  const cmdRes = await fetch(`${backendUrl}/api/unified/timeline?limit=20`, {
    cache: "no-store",
    headers: session?.access_token ? { Authorization: `Bearer ${session.access_token}` } : undefined,
  });
  const cmdJson = (await cmdRes.json()) as { commands?: { id: string; user_prompt?: string; command: string; status: string; provider?: string; project_name?: string; created_at: string }[] };
  const recentCommands = cmdJson.commands ?? [];

  const activity = [
    ...tasks.map((t) => ({ id: t.id, label: t.description, project: t.project_name ?? null, status: t.status, time: t.created_at, type: "task" as const })),
    ...recentCommands.map((c) => ({ id: c.id, label: c.user_prompt || c.command, project: c.project_name ?? null, status: c.status, time: c.created_at, type: "command" as const })),
  ].sort((a, b) => new Date(b.time).getTime() - new Date(a.time).getTime()).slice(0, 20);

  return (
    <div className="max-w-6xl mx-auto space-y-4">
      <DashboardPoller intervalMs={5000} />

      {/* Command Center — the hero of the page */}
      <UnifiedCommandCenter projects={projects.map((p) => ({ id: p.id, name: p.name }))} />

      {/* Bottom panels */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        {/* Projects — narrow left column */}
        <Card className="lg:col-span-1">
          <CardHeader className="pb-2">
            <div className="flex items-center justify-between">
              <CardTitle className="text-sm font-medium">Projects</CardTitle>
              <CreateProjectDialog userId={user.id} />
            </div>
          </CardHeader>
          <CardContent className="p-0">
            {projects.length === 0 ? (
              <div className="px-6 py-10 text-center">
                <p className="text-sm text-muted-foreground">No projects yet</p>
                <p className="text-xs text-muted-foreground/60 mt-1">Create one to get started</p>
              </div>
            ) : (
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Name</TableHead>
                    <TableHead className="text-right w-14">Tasks</TableHead>
                    <TableHead className="text-right w-14">Done</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {projects.map((p) => (
                    <TableRow key={p.id}>
                      <TableCell className="font-medium text-sm">
                        <div className="flex items-center gap-1.5">
                          <span className="truncate">{p.name}</span>
                          <DeleteProjectButton projectId={p.id} />
                        </div>
                      </TableCell>
                      <TableCell className="text-right tabular-nums text-sm text-muted-foreground">{p.total_tasks ?? 0}</TableCell>
                      <TableCell className="text-right tabular-nums text-sm text-emerald-400">{p.completed_tasks ?? 0}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            )}
          </CardContent>
        </Card>

        {/* Recent Activity — wider right column */}
        <div className="lg:col-span-2">
          <RecentActivityCard activity={activity} />
        </div>
      </div>
    </div>
  );
}
