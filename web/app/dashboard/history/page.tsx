import { createClient } from "@/lib/supabase/server";
import { redirect } from "next/navigation";
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
  const {
    data: { session },
  } = await supabase.auth.getSession();

  if (!user) redirect("/login");

  const backendUrl = process.env.BACKEND_URL ?? process.env.NEXT_PUBLIC_BACKEND_URL ?? "http://localhost:8000";
  const res = await fetch(`${backendUrl}/api/call-sessions/${user.id}`, {
    cache: "no-store",
    headers: session?.access_token ? { Authorization: `Bearer ${session.access_token}` } : undefined,
  });
  const json = (await res.json()) as { sessions: CallSession[] };
  const sessions = json.sessions ?? [];

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold tracking-tight">Call History</h1>

      <Card className="bg-dark-card border-dark-border overflow-hidden">
        <CardHeader className="bg-black/40 px-4 py-2 border-b border-white/5 space-y-0 pb-2">
          <CardTitle className="text-xs font-mono text-gray-500 font-normal">SESSIONS</CardTitle>
        </CardHeader>
        <CardContent className="p-4">
          <Table>
            <TableHeader>
              <TableRow className="border-white/5">
                <TableHead className="text-gray-400 py-2">Started</TableHead>
                <TableHead className="text-gray-400 py-2">Duration</TableHead>
                <TableHead className="text-gray-400 py-2">Phone</TableHead>
                <TableHead className="text-gray-400 py-2">Transcript</TableHead>
                <TableHead className="text-gray-400 py-2">Commands</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody className="text-gray-200">
              {sessions.map((s) => {
                const start = new Date(s.started_at);
                const end = s.ended_at ? new Date(s.ended_at) : null;
                const durationSecs = end
                  ? Math.round((end.getTime() - start.getTime()) / 1000)
                  : null;
                const isOngoing = durationSecs === null;

                return (
                  <TableRow key={s.id} className="border-white/5 align-top">
                    <TableCell className="py-2 whitespace-nowrap">{start.toLocaleString()}</TableCell>
                    <TableCell className="py-2">
                      {isOngoing ? (
                        <Badge variant="outline" className="text-[10px] border-blue-500/20 bg-blue-500/15 text-blue-400">
                          ongoing
                        </Badge>
                      ) : (
                        `${durationSecs}s`
                      )}
                    </TableCell>
                    <TableCell className="py-2">{s.phone_number ?? "—"}</TableCell>
                    <TableCell className="py-2 max-w-xs truncate">{s.transcript ?? "—"}</TableCell>
                    <TableCell className="py-2">{s.commands_executed ?? "—"}</TableCell>
                  </TableRow>
                );
              })}
              {sessions.length === 0 && (
                <TableRow>
                  <TableCell className="py-3 text-gray-500" colSpan={5}>
                    No call sessions yet.
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
