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

type ProjectRow = {
  id: string;
  name: string;
  status: string | null;
  total_tasks: number | null;
  pending_tasks: number | null;
  in_progress_tasks: number | null;
  completed_tasks: number | null;
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
  const dashJson = (await dashRes.json()) as { projects: ProjectRow[] };

  const projects = dashJson.projects ?? [];

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

      {/* Projects */}
      <div>
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
      </div>
    </div>
  );
}
