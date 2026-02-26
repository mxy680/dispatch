import { redirect } from "next/navigation";
import { createClient } from "@/lib/supabase/server";
import Link from "next/link";

type CallSession = {
  id: string;
  user_id: string;
  phone_number: string | null;
  started_at: string;
  ended_at: string | null;
  transcript: string | null;
  commands_executed: string | null;
};

export default async function HistoryPage() {
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();

  if (!user) redirect("/login");

  const backendUrl = process.env.NEXT_PUBLIC_BACKEND_URL ?? "http://localhost:8000";
  const res = await fetch(`${backendUrl}/api/call-sessions/${user.id}`, {
    cache: "no-store",
  });
  const json = (await res.json()) as { sessions: CallSession[] };
  const sessions = json.sessions ?? [];

  return (
    <main className="min-h-screen bg-dark-bg p-4 flex flex-col items-center gap-8">
      <div className="w-full max-w-5xl flex items-center justify-between pt-4">
        <h1 className="text-2xl font-bold tracking-tight">Call History</h1>
        <Link
          href="/dashboard"
          className="text-sm text-gray-400 hover:text-white transition-colors"
        >
          ← Back to Dashboard
        </Link>
      </div>

      <section className="w-full max-w-5xl bg-dark-card border border-dark-border rounded-xl overflow-hidden">
        <div className="bg-black/40 px-4 py-2 border-b border-white/5">
          <span className="text-xs font-mono text-gray-500">SESSIONS</span>
        </div>
        <div className="p-4 overflow-auto">
          <table className="w-full text-sm">
            <thead className="text-gray-400">
              <tr>
                <th className="text-left py-2">Started</th>
                <th className="text-left py-2">Duration</th>
                <th className="text-left py-2">Phone</th>
                <th className="text-left py-2">Transcript</th>
                <th className="text-left py-2">Commands</th>
              </tr>
            </thead>
            <tbody className="text-gray-200">
              {sessions.map((s) => {
                const start = new Date(s.started_at);
                const end = s.ended_at ? new Date(s.ended_at) : null;
                const duration = end
                  ? `${Math.round((end.getTime() - start.getTime()) / 1000)}s`
                  : "ongoing";

                return (
                  <tr key={s.id} className="border-t border-white/5 align-top">
                    <td className="py-2 whitespace-nowrap">{start.toLocaleString()}</td>
                    <td className="py-2">{duration}</td>
                    <td className="py-2">{s.phone_number ?? "—"}</td>
                    <td className="py-2 max-w-xs truncate">{s.transcript ?? "—"}</td>
                    <td className="py-2">{s.commands_executed ?? "—"}</td>
                  </tr>
                );
              })}
              {sessions.length === 0 && (
                <tr>
                  <td className="py-3 text-gray-500" colSpan={5}>
                    No call sessions yet.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </section>
    </main>
  );
}