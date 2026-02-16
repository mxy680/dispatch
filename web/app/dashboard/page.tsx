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
    <main className="min-h-screen bg-dark-bg p-4 flex flex-col items-center justify-center gap-12">
      <div className="text-center space-y-2">
        <h1 className="text-4xl font-bold tracking-tight">CallStack</h1>
        <p className="text-gray-400">
          Connected as <span className="text-supabase-green font-mono">{user.phone}</span>
        </p>
      </div>

      <div className="w-full max-w-2xl">
        <VoiceRecorder />
      </div>
      
      <form action="/auth/signout" method="post" className="mt-8">
        <button className="text-sm text-gray-600 hover:text-red-400 transition-colors">
          Sign Out
        </button>
      </form>
    </main>
  );
}