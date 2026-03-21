import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { UnifiedCommandCenter } from "./unified-command-center";

vi.mock("@/lib/supabase/access-token", () => ({
  getAuthHeader: vi.fn().mockResolvedValue(null),
  authFetch: vi.fn().mockResolvedValue({ ok: true, json: () => Promise.resolve({}) }),
}));

describe("UnifiedCommandCenter", () => {
  it("renders unified command center shell", () => {
    render(
      <UnifiedCommandCenter
        projects={[
          { id: "p1", name: "Project One" },
          { id: "p2", name: "Project Two" },
        ]}
      />
    );
    expect(screen.getByText("UNIFIED COMMAND CENTER")).toBeInTheDocument();
    expect(screen.getByPlaceholderText("Type what you want the coding agent to do")).toBeInTheDocument();
  });
});

