import { beforeEach, describe, expect, it, vi } from "vitest";

const getSessionMock = vi.fn();
const refreshSessionMock = vi.fn();

vi.mock("@/lib/supabase/client", () => ({
  createClient: () => ({
    auth: {
      getSession: getSessionMock,
      refreshSession: refreshSessionMock,
    },
  }),
}));

function makeJwt(expInSeconds: number): string {
  const header = btoa(JSON.stringify({ alg: "HS256", typ: "JWT" }));
  const payload = btoa(JSON.stringify({ exp: expInSeconds }));
  return `${header}.${payload}.fakesig`;
}

describe("access-token helper", () => {
  beforeEach(() => {
    vi.resetModules();
    window.localStorage.clear();
    getSessionMock.mockReset();
    refreshSessionMock.mockReset();
  });

  it("uses cached token from localStorage when not expired", async () => {
    const futureExp = Math.floor(Date.now() / 1000) + 3600;
    const validJwt = makeJwt(futureExp);
    window.localStorage.setItem("callstack_access_token", validJwt);
    const { getAuthHeader } = await import("./access-token");
    const header = await getAuthHeader();
    expect(header).toEqual({ Authorization: `Bearer ${validJwt}` });
  });

  it("refreshes when cached token is expired", async () => {
    const pastExp = Math.floor(Date.now() / 1000) - 60;
    window.localStorage.setItem("callstack_access_token", makeJwt(pastExp));

    const futureExp = Math.floor(Date.now() / 1000) + 3600;
    const freshJwt = makeJwt(futureExp);

    getSessionMock.mockResolvedValue({ data: { session: null } });
    refreshSessionMock.mockResolvedValue({
      data: { session: { access_token: freshJwt } },
      error: null,
    });

    const { getAuthHeader } = await import("./access-token");
    const header = await getAuthHeader();
    expect(header).toEqual({ Authorization: `Bearer ${freshJwt}` });
  });

  it("returns null when no token is available anywhere", async () => {
    getSessionMock.mockResolvedValue({ data: { session: null } });
    refreshSessionMock.mockResolvedValue({ data: { session: null }, error: new Error("no session") });

    const { getAuthHeader } = await import("./access-token");
    const header = await getAuthHeader(true);
    expect(header).toBeNull();
  });
});
