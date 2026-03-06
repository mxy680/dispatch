import { createClient } from "@/lib/supabase/server";
import { redirect } from "next/navigation";
import { VoiceRecorder } from "@/components/voice-recorder";
import { AgentStatusPanel } from "@/components/agent-status-panel";
import { TerminalAccessToggle } from "@/components/terminal-access-toggle";
import { DispatchButton } from "@/components/dispatch-button";
import { TerminalConsole } from "@/components/terminal-console";

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

export default async function DashboardPage() {
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();

  if (!user) redirect("/login");

  const backendUrl = process.env.BACKEND_URL ?? process.env.NEXT_PUBLIC_BACKEND_URL ?? "http://localhost:8000";
  const dashRes = await fetch(`${backendUrl}/api/dashboard/${user.id}`, { cache: "no-store" });
  const dashJson = (await dashRes.json()) as { projects: ProjectRow[]; tasks: TaskRow[] };

  const apiDebug = {
    status: dashRes.status,
    ok: dashRes.ok,
    userId: user.id,
    projectsCount: dashJson?.projects?.length ?? 0,
    tasksCount: dashJson?.tasks?.length ?? 0,
  };

  const projects = dashJson.projects ?? [];
  const tasks = dashJson.tasks ?? [];

  return (
    <div className="space-y-8">
      <div className="max-w-2xl mx-auto space-y-6">
        <TerminalAccessToggle userId={user.id} />
        <VoiceRecorder />
      </div>

      <section className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2 space-y-6">
          <div className="bg-dark-card border border-dark-border rounded-xl overflow-hidden">
            <div className="bg-black/40 px-4 py-2 border-b border-white/5">
              <span className="text-xs font-mono text-gray-500">PROJECTS</span>
            </div>
            <div className="p-4 overflow-auto">
              <table className="w-full text-sm">
                <thead className="text-gray-400">
                  <tr>
                    <th className="text-left py-2">Name</th>
                    <th className="text-left py-2">Status</th>
                    <th className="text-right py-2">Total</th>
                    <th className="text-right py-2">Pending</th>
                    <th className="text-right py-2">In progress</th>
                    <th className="text-right py-2">Done</th>
                  </tr>
                </thead>
                <tbody className="text-gray-200">
                  {projects.map((p) => (
                    <tr key={p.id} className="border-t border-white/5">
                      <td className="py-2">{p.name}</td>
                      <td className="py-2">{p.status ?? "active"}</td>
                      <td className="py-2 text-right">{p.total_tasks ?? 0}</td>
                      <td className="py-2 text-right">{p.pending_tasks ?? 0}</td>
                      <td className="py-2 text-right">{p.in_progress_tasks ?? 0}</td>
                      <td className="py-2 text-right">{p.completed_tasks ?? 0}</td>
                    </tr>
                  ))}
                  {projects.length === 0 && (
                    <tr>
                      <td className="py-3 text-gray-500" colSpan={6}>
                        No projects yet.
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>

          <div className="bg-dark-card border border-dark-border rounded-xl overflow-hidden">
            <div className="bg-black/40 px-4 py-2 border-b border-white/5">
              <span className="text-xs font-mono text-gray-500">TASKS</span>
            </div>
            <div className="p-4 overflow-auto">
              <table className="w-full text-sm">
                <thead className="text-gray-400">
                  <tr>
                    <th className="text-left py-2">Project</th>
                    <th className="text-left py-2">Description</th>
                    <th className="text-left py-2">Intent</th>
                    <th className="text-left py-2">Status</th>
                    <th className="text-left py-2">Actions</th>
                  </tr>
                </thead>
                <tbody className="text-gray-200">
                  {tasks.map((t) => (
                    <tr key={t.id} className="border-t border-white/5 align-top">
                      <td className="py-2">{t.project_name ?? t.project_id}</td>
                      <td className="py-2 max-w-xs truncate">{t.description}</td>
                      <td className="py-2">{t.intent_type ?? "-"}</td>
                      <td className="py-2">
                        <span
                          className={`px-2 py-1 rounded-full text-xs font-mono ${
                            t.status === "completed" || t.status === "agent_completed"
                              ? "bg-green-500/20 text-green-400"
                              : t.status === "agent_dispatched"
                              ? "bg-purple-500/20 text-purple-400"
                              : t.status === "in_progress"
                              ? "bg-blue-500/20 text-blue-400"
                              : "bg-yellow-500/20 text-yellow-400"
                          }`}
                        >
                          {t.status}
                        </span>
                      </td>
                      <td className="py-2">
                        <DispatchButton taskId={t.id} />
                      </td>
                    </tr>
                  ))}
                  {tasks.length === 0 && (
                    <tr>
                      <td className="py-3 text-gray-500" colSpan={5}>
                        No tasks yet.
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>
        </div>

        <div className="space-y-6">
          <AgentStatusPanel userId={user.id} />
          <TerminalConsole projects={projects.map((p) => ({ id: p.id, name: p.name }))} />
        </div>
      </section>

      <details className="bg-dark-card border border-dark-border rounded-xl p-4">
        <summary className="text-xs font-mono text-gray-400 cursor-pointer">DEBUG: /api/dashboard response</summary>
        <pre className="mt-3 text-xs text-gray-300 overflow-auto">
          {JSON.stringify({ apiDebug, dashJson }, null, 2)}
        </pre>
      </details>
    </div>
  );
}
