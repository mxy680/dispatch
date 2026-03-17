import { redirect } from "next/navigation";
import Link from "next/link";
import { createClient } from "@/lib/supabase/server";
import { SettingsAgentsPanel } from "@/components/settings-agents-panel";
import { SettingsDangerZone } from "@/components/settings-danger-zone";

export default async function SettingsPage() {
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();

  if (!user) redirect("/login");

  return (
    <main className="min-h-screen bg-dark-bg p-4 flex flex-col items-center gap-8">
      <div className="w-full max-w-5xl flex items-center justify-between pt-4">
        <h1 className="text-2xl font-bold tracking-tight">Settings</h1>
        <div className="flex items-center gap-4">
          <Link href="/dashboard" className="text-sm text-gray-400 hover:text-white transition-colors">
            ← Back to Dashboard
          </Link>
        </div>
      </div>

      <section className="w-full max-w-5xl grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2 space-y-6">
          <SettingsAgentsPanel />
          <SettingsDangerZone />
        </div>

        <div className="space-y-6">
          <div className="bg-dark-card border border-dark-border rounded-xl p-6">
            <h3 className="text-sm font-mono text-gray-400 uppercase tracking-wider mb-2">Account</h3>
            <p className="text-sm text-gray-300">
              Signed in as{" "}
              <span className="text-supabase-green font-mono">{user.phone || user.email}</span>
            </p>
            <form action="/auth/signout" method="post" className="mt-4">
              <button className="text-sm text-gray-600 hover:text-red-400 transition-colors">
                Sign Out
              </button>
            </form>
          </div>
        </div>
      </section>
    </main>
  );
}

