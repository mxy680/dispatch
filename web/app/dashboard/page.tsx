import { redirect } from "next/navigation";
import { createClient } from "@/lib/supabase/server";

export default async function DashboardPage() {
  const supabase = await createClient();
  const { data: { user } } = await supabase.auth.getUser();

  if (!user) {
    redirect("/login");
  }

  return (
    <main className="min-h-screen flex items-center justify-center p-4">
      <div className="bg-dark-card border border-dark-border rounded-lg p-8 max-w-md w-full">
        <h1 className="text-2xl font-semibold mb-4">Dashboard</h1>
        <p className="text-gray-400 mb-4">
          Signed in as: {user.phone}
        </p>
        <form action="/auth/signout" method="post">
          <button
            type="submit"
            className="w-full py-3 bg-dark-border text-white font-medium rounded-md hover:bg-gray-600 transition-colors"
          >
            Sign Out
          </button>
        </form>
      </div>
    </main>
  );
}
