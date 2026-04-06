"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { authFetch } from "@/lib/supabase/access-token";
import { Button } from "@/components/ui/button";

export function DeleteProjectButton({ projectId }: { projectId: string }) {
  const backendUrl = process.env.NEXT_PUBLIC_BACKEND_URL ?? "http://localhost:8000";
  const router = useRouter();
  const [deleting, setDeleting] = useState(false);

  const handleDelete = async () => {
    if (!confirm("Delete this project and all its data?")) return;
    setDeleting(true);
    try {
      await authFetch(`${backendUrl}/api/projects/${projectId}`, { method: "DELETE" });
      router.refresh();
    } catch {
      alert("Failed to delete project");
    } finally {
      setDeleting(false);
    }
  };

  return (
    <Button
      variant="ghost"
      size="sm"
      onClick={handleDelete}
      disabled={deleting}
      className="text-xs text-muted-foreground hover:text-red-400 transition-colors"
      title="Delete project"
    >
      {deleting ? "..." : "×"}
    </Button>
  );
}
