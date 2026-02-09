// web/app/dashboard/page.tsx
import { redirect } from "next/navigation";
import { createClient } from "@/lib/supabase/server";
import { VoiceRecorder } from "@/components/voice-recorder";

export default async function DashboardPage() {
  const supabase = await createClient();
  const { data: { user } } = await supabase.auth.getUser();

  if (!user) {
    redirect("/login");
  }

  return (
    <main className="min-h-screen bg-dark-bg p-4 flex flex-col items-center justify-center gap-8">
      <div className="text-center space-y-2">
        <h1 className="text-3xl font-bold tracking-tight">CallStack Agent</h1>
        <p className="text-gray-400">
          Orchestrating as <span className="text-supabase-green font-mono">{user.phone}</span>
        </p>
      </div>

      <VoiceRecorder />
      
      {/* Sign Out (Keep this for convenience) */}
      <form action="/auth/signout" method="post" className="mt-8">
        <button className="text-sm text-gray-500 hover:text-white transition-colors">
          Sign Out
        </button>
      </form>
    </main>
  );
}