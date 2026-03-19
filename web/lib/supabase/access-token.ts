import { createClient } from "@/lib/supabase/client";

let cachedToken: string | null = null;
let cacheTs = 0;
const LS_KEY = "callstack_access_token";
const LS_TS_KEY = "callstack_access_token_ts";

// Cache token for up to 24 hours; Supabase will still 401 if it's actually invalid.
const CACHE_MS = 24 * 60 * 60 * 1000; // 24 hours

function loadFromStorage() {
  if (typeof window === "undefined") return;
  if (cachedToken) return;
  const token = window.localStorage.getItem(LS_KEY);
  const tsRaw = window.localStorage.getItem(LS_TS_KEY);
  const ts = tsRaw ? Number(tsRaw) : 0;
  if (token && ts) {
    cachedToken = token;
    cacheTs = ts;
  }
}

function saveToStorage(token: string | null, ts: number) {
  if (typeof window === "undefined") return;
  if (!token) return;
  window.localStorage.setItem(LS_KEY, token);
  window.localStorage.setItem(LS_TS_KEY, String(ts));
}

export async function getAccessToken(): Promise<string | null> {
  loadFromStorage();
  const now = Date.now();
  if (cachedToken && now - cacheTs < CACHE_MS) return cachedToken;

  const supabase = createClient();

  // Prefer getSession (cheap, no refresh).
  const { data: sessionData } = await supabase.auth.getSession();
  const token = sessionData.session?.access_token ?? null;
  if (token) {
    cachedToken = token;
    cacheTs = now;
    saveToStorage(token, now);
    return token;
  }

  // Fallback: refresh once if needed.
  const { data, error } = await supabase.auth.refreshSession();
  if (error) return null;
  const refreshed = data.session?.access_token ?? null;
  if (refreshed) {
    cachedToken = refreshed;
    cacheTs = now;
    saveToStorage(refreshed, now);
  }
  // If refresh fails to produce a token, keep previous cached token as best-effort.
  if (!refreshed && cachedToken) return cachedToken;
  return refreshed;
}

export async function getAuthHeader(): Promise<{ Authorization: string } | null> {
  const token = await getAccessToken();
  if (!token) return null;
  return { Authorization: `Bearer ${token}` };
}

