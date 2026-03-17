import { createClient } from "@/lib/supabase/client";

let cachedToken: string | null = null;
let cacheTs = 0;

// Keep it short; if expired, requests will 401 and we can refetch.
const CACHE_MS = 30_000;

export async function getAccessToken(): Promise<string | null> {
  const now = Date.now();
  if (cachedToken && now - cacheTs < CACHE_MS) return cachedToken;

  const supabase = createClient();

  // Prefer getSession (cheap, no refresh).
  const { data: sessionData } = await supabase.auth.getSession();
  const token = sessionData.session?.access_token ?? null;
  if (token) {
    cachedToken = token;
    cacheTs = now;
    return token;
  }

  // Fallback: refresh once if needed.
  const { data, error } = await supabase.auth.refreshSession();
  if (error) return null;
  const refreshed = data.session?.access_token ?? null;
  cachedToken = refreshed;
  cacheTs = now;
  return refreshed;
}

export async function getAuthHeader(): Promise<{ Authorization: string } | null> {
  const token = await getAccessToken();
  if (!token) return null;
  return { Authorization: `Bearer ${token}` };
}

