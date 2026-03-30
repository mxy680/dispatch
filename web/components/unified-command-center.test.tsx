import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { UnifiedCommandCenter } from "./unified-command-center";
import { authFetch } from "@/lib/supabase/access-token";

vi.mock("@/lib/supabase/access-token", () => ({
  authFetch: vi.fn(),
}));

describe("UnifiedCommandCenter", () => {
  it("renders command controls and conversation section", () => {
    vi.mocked(authFetch).mockResolvedValue({
      ok: true,
      json: async () => ({ commands: [], turns: [] }),
    } as Response);
    render(
      <UnifiedCommandCenter
        projects={[
          { id: "p1", name: "Project One" },
        ]}
      />
    );
    expect(screen.getByText("Voice: Off")).toBeInTheDocument();
    expect(screen.getByPlaceholderText("Describe what you want the agent to do...")).toBeInTheDocument();
  });
});

