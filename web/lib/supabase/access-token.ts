import { createClient } from "@/lib/supabase/client";

let cachedToken: string | null = null;
const LS_KEY = "callstack_access_token";

const REFRESH_MARGIN_S = 60;

function getJwtExp(token: string): number | null {
  try {
    const payload = token.split(".")[1];
    if (!payload) return null;
    const decoded = JSON.parse(atob(payload));
    return typeof decoded.exp === "number" ? decoded.exp : null;
  } catch {
    return null;
  }
}

function isTokenUsable(token: string | null): boolean {
  if (!token) return false;
  const exp = getJwtExp(token);
  if (!exp) return false;
  return exp - REFRESH_MARGIN_S > Date.now() / 1000;
}

function loadFromStorage(): string | null {
  if (typeof window === "undefined") return null;
  if (cachedToken && isTokenUsable(cachedToken)) return cachedToken;
  const stored = window.localStorage.getItem(LS_KEY);
  if (stored && isTokenUsable(stored)) {
    cachedToken = stored;
    return stored;
  }
  return null;
}

function saveToStorage(token: string) {
  cachedToken = token;
  if (typeof window !== "undefined") {
    window.localStorage.setItem(LS_KEY, token);
  }
}

function clearCache() {
  cachedToken = null;
  if (typeof window !== "undefined") {
    window.localStorage.removeItem(LS_KEY);
  }
}

function sleep(ms: number) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

export async function getAccessToken(forceRefresh = false): Promise<string | null> {
  if (!forceRefresh) {
    const usable = loadFromStorage();
    if (usable) return usable;
  }

  clearCache();
  const supabase = createClient();

  for (let attempt = 0; attempt < 3; attempt++) {
    const { data: sessionData } = await supabase.auth.getSession();
    const token = sessionData.session?.access_token ?? null;
    if (token && isTokenUsable(token)) {
      saveToStorage(token);
      return token;
    }
    await sleep(150 * (attempt + 1));
  }

  const { data, error } = await supabase.auth.refreshSession();
  if (!error) {
    const refreshed = data.session?.access_token ?? null;
    if (refreshed && isTokenUsable(refreshed)) {
      saveToStorage(refreshed);
      return refreshed;
    }
  }

  return null;
}

export async function getAuthHeader(forceRefresh = false): Promise<{ Authorization: string } | null> {
  const token = await getAccessToken(forceRefresh);
  if (!token) return null;
  return { Authorization: `Bearer ${token}` };
}

export async function authFetch(url: string, init?: RequestInit): Promise<Response> {
  let auth = await getAuthHeader();
  if (!auth) auth = await getAuthHeader(true);
  if (!auth) throw new Error("No auth token available. Please sign in again.");

  const res = await fetch(url, {
    ...init,
    headers: { ...init?.headers, ...auth },
  });

  if (res.status === 401) {
    const freshAuth = await getAuthHeader(true);
    if (!freshAuth) throw new Error("Session expired. Please sign in again.");
    const retry = await fetch(url, {
      ...init,
      headers: { ...init?.headers, ...freshAuth },
    });
    return retry;
  }

  return res;
}
