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

function sleep(ms: number) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

export async function getAccessToken(forceRefresh = false): Promise<string | null> {
  loadFromStorage();
  const now = Date.now();
  if (!forceRefresh && cachedToken && now - cacheTs < CACHE_MS) return cachedToken;

  const supabase = createClient();

  // Retry a few times because Supabase session hydration can be briefly delayed.
  for (let attempt = 0; attempt < 3; attempt++) {
    const { data: sessionData } = await supabase.auth.getSession();
    const token = sessionData.session?.access_token ?? null;
    if (token) {
      cachedToken = token;
      cacheTs = Date.now();
      saveToStorage(token, cacheTs);
      return token;
    }
    await sleep(100 * (attempt + 1));
  }

  // Fallback: refresh once if needed.
  const { data, error } = await supabase.auth.refreshSession();
  if (error) return cachedToken;
  const refreshed = data.session?.access_token ?? null;
  if (refreshed) {
    cachedToken = refreshed;
    cacheTs = Date.now();
    saveToStorage(refreshed, cacheTs);
    return refreshed;
  }
  // If refresh fails to produce a token, keep previous cached token as best-effort.
  return cachedToken;
}

export async function getAuthHeader(forceRefresh = false): Promise<{ Authorization: string } | null> {
  const token = await getAccessToken(forceRefresh);
  if (!token) return null;
  return { Authorization: `Bearer ${token}` };
}

