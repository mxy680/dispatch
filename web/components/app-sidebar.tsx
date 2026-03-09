"use client";

import { usePathname } from "next/navigation";
import Link from "next/link";
import {
  RiDashboardLine,
  RiHistoryLine,
  RiSettings3Line,
  RiLogoutBoxRLine,
  RiPhoneLine,
} from "@remixicon/react";
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarGroup,
  SidebarGroupContent,
  SidebarGroupLabel,
  SidebarHeader,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
} from "@/components/ui/sidebar";
import { Separator } from "@/components/ui/separator";

const navItems = [
  { title: "Dashboard", href: "/dashboard", icon: RiDashboardLine },
  { title: "Call History", href: "/dashboard/history", icon: RiHistoryLine },
  { title: "Settings", href: "/dashboard/settings", icon: RiSettings3Line },
];

type AppSidebarProps = {
  userDisplay: string;
};

export function AppSidebar({ userDisplay }: AppSidebarProps) {
  const pathname = usePathname();

  return (
    <Sidebar>
      <SidebarHeader className="p-4">
        <div className="flex items-center gap-2">
          <RiPhoneLine className="h-5 w-5 text-primary" />
          <span className="text-lg font-bold tracking-tight">Dispatch</span>
        </div>
      </SidebarHeader>

      <Separator />

      <SidebarContent>
        <SidebarGroup>
          <SidebarGroupLabel>Navigation</SidebarGroupLabel>
          <SidebarGroupContent>
            <SidebarMenu>
              {navItems.map((item) => {
                const isActive =
                  item.href === "/dashboard"
                    ? pathname === "/dashboard"
                    : pathname.startsWith(item.href);

                return (
                  <SidebarMenuItem key={item.href}>
                    <SidebarMenuButton asChild isActive={isActive}>
                      <Link href={item.href}>
                        <item.icon className="h-4 w-4" />
                        <span>{item.title}</span>
                      </Link>
                    </SidebarMenuButton>
                  </SidebarMenuItem>
                );
              })}
            </SidebarMenu>
          </SidebarGroupContent>
        </SidebarGroup>
      </SidebarContent>

      <SidebarFooter className="p-4">
        <Separator className="mb-3" />
        <p className="text-xs text-muted-foreground truncate mb-2">
          {userDisplay}
        </p>
        <form action="/auth/signout" method="post">
          <button
            type="submit"
            className="flex items-center gap-2 text-xs text-muted-foreground hover:text-destructive transition-colors"
          >
            <RiLogoutBoxRLine className="h-3.5 w-3.5" />
            Sign Out
          </button>
        </form>
      </SidebarFooter>
    </Sidebar>
  );
}
