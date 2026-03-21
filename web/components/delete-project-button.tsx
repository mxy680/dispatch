"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { authFetch } from "@/lib/supabase/access-token";

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
    <button
      onClick={handleDelete}
      disabled={deleting}
      className="text-xs text-muted-foreground hover:text-red-400 transition-colors disabled:opacity-50"
      title="Delete project"
    >
      {deleting ? "..." : "×"}
    </button>
  );
}
