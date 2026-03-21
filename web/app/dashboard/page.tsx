import { redirect } from "next/navigation";
import { createClient } from "@/lib/supabase/server";
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

export default async function DashboardPage() {
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();

  if (!user) redirect("/login");
  const {
    data: { session },
  } = await supabase.auth.getSession();

  const backendUrl = process.env.NEXT_PUBLIC_BACKEND_URL ?? "http://localhost:8000";
  const dashRes = await fetch(`${backendUrl}/api/dashboard/${user.id}`, {
    cache: "no-store",
    headers: session?.access_token ? { Authorization: `Bearer ${session.access_token}` } : undefined,
  });
  const dashJson = (await dashRes.json()) as { projects: ProjectRow[]; tasks: TaskRow[] };

  const projects = dashJson.projects ?? [];
  const tasks = dashJson.tasks ?? [];

  return (
    <main className="min-h-screen bg-dark-bg p-4 md:p-6 flex flex-col items-center gap-6">
      <div className="w-full max-w-6xl flex items-center justify-between">
        <div className="space-y-1">
          <h1 className="text-3xl font-bold tracking-tight">CallStack</h1>
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

      <div className="w-full max-w-6xl">
        <TerminalAccessToggle userId={user.id} />
      </div>

      <div className="w-full max-w-6xl">
        <UnifiedCommandCenter projects={projects.map((p) => ({ id: p.id, name: p.name }))} />
      </div>

      <section className="w-full max-w-6xl grid grid-cols-1 lg:grid-cols-2 gap-6">
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
                    <td className="py-2 text-right">{p.completed_tasks ?? 0}</td>
                  </tr>
                ))}
                {projects.length === 0 && (
                  <tr>
                    <td className="py-3 text-gray-500" colSpan={5}>
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
            <span className="text-xs font-mono text-gray-500">RECENT TASKS</span>
          </div>
          <div className="p-4 overflow-auto">
            <table className="w-full text-sm">
              <thead className="text-gray-400">
                <tr>
                  <th className="text-left py-2">Project</th>
                  <th className="text-left py-2">Description</th>
                  <th className="text-left py-2">Status</th>
                </tr>
              </thead>
              <tbody className="text-gray-200">
                {tasks.map((t) => (
                  <tr key={t.id} className="border-t border-white/5 align-top">
                    <td className="py-2">{t.project_name ?? t.project_id}</td>
                    <td className="py-2 max-w-xs truncate">{t.description}</td>
                    <td className="py-2">{t.status}</td>
                  </tr>
                ))}
                {tasks.length === 0 && (
                  <tr>
                    <td className="py-3 text-gray-500" colSpan={3}>
                      No tasks yet.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      </section>

      <form action="/auth/signout" method="post" className="mt-4">
        <button className="text-sm text-gray-600 hover:text-red-400 transition-colors">Sign Out</button>
      </form>
    </main>
  );
}
