import { redirect } from "next/navigation";
import { createClient } from "@/lib/supabase/server";
import { SidebarInset, SidebarProvider, SidebarTrigger } from "@/components/ui/sidebar";
import { AppSidebar } from "@/components/app-sidebar";
import { TooltipProvider } from "@/components/ui/tooltip";
import { PhoneOnboardingDialog } from "@/components/phone-onboarding-dialog";

const BACKEND_URL =
  process.env.BACKEND_URL ??
  process.env.NEXT_PUBLIC_BACKEND_URL ??
  "http://localhost:8000";

export default async function DashboardLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();

  if (!user) redirect("/login");

  const userDisplay = user.phone || user.email || "Unknown";

  // Fetch the session access token to call the backend on the server side.
  const {
    data: { session },
  } = await supabase.auth.getSession();

  let hasPhone = false;
  if (session?.access_token) {
    try {
      const res = await fetch(`${BACKEND_URL}/api/phone/status`, {
        headers: { Authorization: `Bearer ${session.access_token}` },
        cache: "no-store",
      });
      if (res.ok) {
        const data = await res.json();
        hasPhone = Boolean(data.has_phone);
      }
    } catch {
      // If the backend is unreachable, default to not showing the dialog.
      hasPhone = true;
    }
  }

  return (
    <TooltipProvider>
      <SidebarProvider>
        <AppSidebar userDisplay={userDisplay} />
        <SidebarInset>
          <header className="flex items-center gap-2 border-b px-4 py-2">
            <SidebarTrigger />
          </header>
          <main className="flex-1 p-6">{children}</main>
        </SidebarInset>
      </SidebarProvider>
      <PhoneOnboardingDialog open={!hasPhone} />
    </TooltipProvider>
  );
}
