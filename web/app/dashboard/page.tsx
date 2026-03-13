import { createClient } from "@/lib/supabase/server";
import { redirect } from "next/navigation";
import { VoiceRecorder } from "@/components/voice-recorder";
import { AgentStatusPanel } from "@/components/agent-status-panel";
import { TerminalAccessToggle } from "@/components/terminal-access-toggle";
import { DispatchButton } from "@/components/dispatch-button";
import { TerminalConsoleWrapper } from "@/components/terminal-console-wrapper";
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

  const completedTasks = tasks.filter((t) => t.status === "completed" || t.status === "agent_completed").length;
  const inProgressTasks = tasks.filter((t) => t.status === "in_progress").length;

  return (
    <div className="grid grid-cols-12 gap-3">
      {/* ── Row 1: Stat cards ── */}
      {[
        { label: "Projects", value: projects.length, color: "" },
        { label: "Total Tasks", value: tasks.length, color: "" },
        { label: "In Progress", value: inProgressTasks, color: "text-blue-400" },
        { label: "Completed", value: completedTasks, color: "text-emerald-400" },
      ].map((stat) => (
        <Card key={stat.label} className="col-span-6 lg:col-span-3">
          <CardContent className="p-4">
            <p className="text-[11px] font-medium text-muted-foreground uppercase tracking-widest">{stat.label}</p>
            <p className={`text-2xl font-semibold mt-0.5 tabular-nums ${stat.color}`}>{stat.value}</p>
          </CardContent>
        </Card>
      ))}

      {/* ── Row 2: Voice + right sidebar stack ── */}
      <div className="col-span-12 lg:col-span-8 min-h-[280px]">
        <VoiceRecorder />
      </div>

      <div className="col-span-12 lg:col-span-4 grid grid-rows-[auto_1fr] gap-3 min-h-[280px]">
        <TerminalAccessToggle userId={user.id} />
        <AgentStatusPanel userId={user.id} />
      </div>

      {/* ── Row 3: Projects + Terminal ── */}
      <Card className="col-span-12 lg:col-span-7 overflow-hidden">
        <CardHeader className="p-4 pb-0">
          <CardTitle className="text-xs font-mono uppercase tracking-widest text-muted-foreground">Projects</CardTitle>
        </CardHeader>
        <CardContent className="p-0 pt-2">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="text-xs">Name</TableHead>
                <TableHead className="text-xs">Status</TableHead>
                <TableHead className="text-xs text-right">Total</TableHead>
                <TableHead className="text-xs text-right">Pending</TableHead>
                <TableHead className="text-xs text-right">Active</TableHead>
                <TableHead className="text-xs text-right">Done</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {projects.map((p) => (
                <TableRow key={p.id}>
                  <TableCell className="font-medium text-sm">{p.name}</TableCell>
                  <TableCell>
                    <Badge variant="outline" className="text-[10px]">{p.status ?? "active"}</Badge>
                  </TableCell>
                  <TableCell className="text-right tabular-nums text-sm">{p.total_tasks ?? 0}</TableCell>
                  <TableCell className="text-right tabular-nums text-sm">{p.pending_tasks ?? 0}</TableCell>
                  <TableCell className="text-right tabular-nums text-sm">{p.in_progress_tasks ?? 0}</TableCell>
                  <TableCell className="text-right tabular-nums text-sm">{p.completed_tasks ?? 0}</TableCell>
                </TableRow>
              ))}
              {projects.length === 0 && (
                <TableRow>
                  <TableCell className="text-muted-foreground text-sm" colSpan={6}>No projects yet.</TableCell>
                </TableRow>
              )}
            </TableBody>
          </Table>
        </CardContent>
      </Card>

      <div className="col-span-12 lg:col-span-5">
        <TerminalConsoleWrapper projects={projects.map((p) => ({ id: p.id, name: p.name }))} />
      </div>

      {/* ── Row 4: Tasks — full width ── */}
      <Card className="col-span-12 overflow-hidden">
        <CardHeader className="p-4 pb-0">
          <CardTitle className="text-xs font-mono uppercase tracking-widest text-muted-foreground">Tasks</CardTitle>
        </CardHeader>
        <CardContent className="p-0 pt-2">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="text-xs">Project</TableHead>
                <TableHead className="text-xs">Description</TableHead>
                <TableHead className="text-xs">Intent</TableHead>
                <TableHead className="text-xs">Status</TableHead>
                <TableHead className="text-xs w-[80px]">Actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {tasks.map((t) => (
                <TableRow key={t.id}>
                  <TableCell className="font-medium text-sm whitespace-nowrap">{t.project_name ?? t.project_id}</TableCell>
                  <TableCell className="max-w-xs truncate text-sm">{t.description}</TableCell>
                  <TableCell>
                    <span className="text-xs text-muted-foreground font-mono">{t.intent_type ?? "—"}</span>
                  </TableCell>
                  <TableCell>
                    <Badge variant="outline" className={`text-[10px] border ${statusVariant(t.status)}`}>{t.status}</Badge>
                  </TableCell>
                  <TableCell>
                    <DispatchButton taskId={t.id} />
                  </TableCell>
                </TableRow>
              ))}
              {tasks.length === 0 && (
                <TableRow>
                  <TableCell className="text-muted-foreground text-sm" colSpan={5}>No tasks yet.</TableCell>
                </TableRow>
              )}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
    </div>
  );
}
