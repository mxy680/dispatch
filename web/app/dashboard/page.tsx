import { createClient } from "@/lib/supabase/server";
import { redirect } from "next/navigation";
import { VoiceRecorder } from "@/components/voice-recorder";
import { AgentStatusPanel } from "@/components/agent-status-panel";
import { TerminalAccessToggle } from "@/components/terminal-access-toggle";
import { DispatchButton } from "@/components/dispatch-button";
import { TerminalConsole } from "@/components/terminal-console";
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
  raw_transcript?: string | null;
};

function statusVariant(status: string) {
  if (status === "completed" || status === "agent_completed") return "bg-emerald-500/15 text-emerald-400 border-emerald-500/20";
  if (status === "agent_dispatched") return "bg-violet-500/15 text-violet-400 border-violet-500/20";
  if (status === "in_progress") return "bg-blue-500/15 text-blue-400 border-blue-500/20";
  return "bg-amber-500/15 text-amber-400 border-amber-500/20";
}

export default async function DashboardPage() {
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();

  if (!user) redirect("/login");

  const backendUrl = process.env.BACKEND_URL ?? process.env.NEXT_PUBLIC_BACKEND_URL ?? "http://localhost:8000";
  const dashRes = await fetch(`${backendUrl}/api/dashboard/${user.id}`, { cache: "no-store" });
  const dashJson = (await dashRes.json()) as { projects: ProjectRow[]; tasks: TaskRow[] };

  const projects = dashJson.projects ?? [];
  const tasks = dashJson.tasks ?? [];

  const totalTasks = tasks.length;
  const completedTasks = tasks.filter((t) => t.status === "completed" || t.status === "agent_completed").length;
  const inProgressTasks = tasks.filter((t) => t.status === "in_progress").length;
  const pendingTasks = tasks.filter((t) => t.status === "pending").length;

  return (
    <div className="grid grid-cols-1 lg:grid-cols-12 gap-4 auto-rows-min">
      {/* Row 1: Stats cards — 4 across */}
      <Card className="lg:col-span-3">
        <CardContent className="pt-6">
          <p className="text-xs font-medium text-muted-foreground uppercase tracking-wider">Projects</p>
          <p className="text-3xl font-bold mt-1">{projects.length}</p>
        </CardContent>
      </Card>
      <Card className="lg:col-span-3">
        <CardContent className="pt-6">
          <p className="text-xs font-medium text-muted-foreground uppercase tracking-wider">Total Tasks</p>
          <p className="text-3xl font-bold mt-1">{totalTasks}</p>
        </CardContent>
      </Card>
      <Card className="lg:col-span-3">
        <CardContent className="pt-6">
          <p className="text-xs font-medium text-muted-foreground uppercase tracking-wider">In Progress</p>
          <p className="text-3xl font-bold mt-1 text-blue-400">{inProgressTasks}</p>
        </CardContent>
      </Card>
      <Card className="lg:col-span-3">
        <CardContent className="pt-6">
          <p className="text-xs font-medium text-muted-foreground uppercase tracking-wider">Completed</p>
          <p className="text-3xl font-bold mt-1 text-emerald-400">{completedTasks}</p>
        </CardContent>
      </Card>

      {/* Row 2: Voice Recorder (wide) + Terminal Access toggle (narrow) */}
      <div className="lg:col-span-8">
        <VoiceRecorder />
      </div>
      <div className="lg:col-span-4 flex flex-col gap-4">
        <TerminalAccessToggle userId={user.id} />
        <AgentStatusPanel userId={user.id} />
      </div>

      {/* Row 3: Projects table (left) + Terminal console (right) */}
      <Card className="lg:col-span-7 overflow-hidden">
        <CardHeader className="pb-3">
          <CardTitle className="text-sm font-mono uppercase tracking-wider text-muted-foreground">Projects</CardTitle>
        </CardHeader>
        <CardContent className="p-0">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Name</TableHead>
                <TableHead>Status</TableHead>
                <TableHead className="text-right">Total</TableHead>
                <TableHead className="text-right">Pending</TableHead>
                <TableHead className="text-right">Active</TableHead>
                <TableHead className="text-right">Done</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {projects.map((p) => (
                <TableRow key={p.id}>
                  <TableCell className="font-medium">{p.name}</TableCell>
                  <TableCell>
                    <Badge variant="outline" className="text-xs">
                      {p.status ?? "active"}
                    </Badge>
                  </TableCell>
                  <TableCell className="text-right tabular-nums">{p.total_tasks ?? 0}</TableCell>
                  <TableCell className="text-right tabular-nums">{p.pending_tasks ?? 0}</TableCell>
                  <TableCell className="text-right tabular-nums">{p.in_progress_tasks ?? 0}</TableCell>
                  <TableCell className="text-right tabular-nums">{p.completed_tasks ?? 0}</TableCell>
                </TableRow>
              ))}
              {projects.length === 0 && (
                <TableRow>
                  <TableCell className="text-muted-foreground" colSpan={6}>
                    No projects yet.
                  </TableCell>
                </TableRow>
              )}
            </TableBody>
          </Table>
        </CardContent>
      </Card>

      <div className="lg:col-span-5">
        <TerminalConsole projects={projects.map((p) => ({ id: p.id, name: p.name }))} />
      </div>

      {/* Row 4: Tasks table — full width */}
      <Card className="lg:col-span-12 overflow-hidden">
        <CardHeader className="pb-3">
          <CardTitle className="text-sm font-mono uppercase tracking-wider text-muted-foreground">Tasks</CardTitle>
        </CardHeader>
        <CardContent className="p-0">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Project</TableHead>
                <TableHead>Description</TableHead>
                <TableHead>Intent</TableHead>
                <TableHead>Status</TableHead>
                <TableHead className="w-[100px]">Actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {tasks.map((t) => (
                <TableRow key={t.id}>
                  <TableCell className="font-medium whitespace-nowrap">{t.project_name ?? t.project_id}</TableCell>
                  <TableCell className="max-w-xs truncate">{t.description}</TableCell>
                  <TableCell>
                    <span className="text-xs text-muted-foreground font-mono">{t.intent_type ?? "—"}</span>
                  </TableCell>
                  <TableCell>
                    <Badge variant="outline" className={`text-xs border ${statusVariant(t.status)}`}>
                      {t.status}
                    </Badge>
                  </TableCell>
                  <TableCell>
                    <DispatchButton taskId={t.id} />
                  </TableCell>
                </TableRow>
              ))}
              {tasks.length === 0 && (
                <TableRow>
                  <TableCell className="text-muted-foreground" colSpan={5}>
                    No tasks yet.
                  </TableCell>
                </TableRow>
              )}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
    </div>
  );
}
