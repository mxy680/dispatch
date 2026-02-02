# Login Component Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Create a phone-based SMS OTP login component with Supabase auth, Next.js frontend in `/web`, and Python FastAPI server in `/server`.

**Architecture:** Next.js App Router with `@supabase/ssr` for auth. Client component for login form with two-step flow (phone entry → OTP verification). Minimal Python server as placeholder for future orchestrator logic.

**Tech Stack:** Next.js 14+, Tailwind CSS, @supabase/ssr, @supabase/supabase-js, Python 3.11+, FastAPI

---

## Task 1: Initialize Next.js Project

**Files:**
- Create: `web/` directory with Next.js app

**Step 1: Create Next.js app with TypeScript and Tailwind**

```bash
cd /Users/markshteyn/projects/dispatch
npx create-next-app@latest web --typescript --tailwind --eslint --app --src-dir=false --import-alias="@/*" --use-npm
```

Select defaults when prompted.

**Step 2: Verify the project was created**

```bash
ls web/app
```

Expected: `layout.tsx`, `page.tsx`, `globals.css`

**Step 3: Commit**

```bash
git add web/
git commit -m "feat: initialize Next.js project in /web"
```

---

## Task 2: Install Supabase Dependencies

**Files:**
- Modify: `web/package.json`

**Step 1: Install Supabase packages**

```bash
cd /Users/markshteyn/projects/dispatch/web
npm install @supabase/supabase-js @supabase/ssr
```

**Step 2: Verify installation**

```bash
grep supabase web/package.json
```

Expected: `@supabase/supabase-js` and `@supabase/ssr` in dependencies

**Step 3: Commit**

```bash
git add web/package.json web/package-lock.json
git commit -m "feat: add Supabase dependencies"
```

---

## Task 3: Configure Tailwind for Dark Theme

**Files:**
- Modify: `web/tailwind.config.ts`
- Modify: `web/app/globals.css`

**Step 1: Update Tailwind config with Supabase green colors**

```typescript
// web/tailwind.config.ts
import type { Config } from "tailwindcss";

export default {
  content: [
    "./pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./components/**/*.{js,ts,jsx,tsx,mdx}",
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        supabase: {
          green: "#3ECF8E",
          "green-dark": "#2da36e",
        },
        dark: {
          bg: "#1a1a1a",
          card: "#242424",
          border: "#333333",
        },
      },
    },
  },
  plugins: [],
} satisfies Config;
```

**Step 2: Update globals.css with dark theme base**

```css
/* web/app/globals.css */
@tailwind base;
@tailwind components;
@tailwind utilities;

:root {
  --background: #1a1a1a;
  --foreground: #ededed;
}

body {
  background: var(--background);
  color: var(--foreground);
  font-family: system-ui, -apple-system, sans-serif;
}
```

**Step 3: Commit**

```bash
git add web/tailwind.config.ts web/app/globals.css
git commit -m "feat: configure Tailwind with Supabase dark theme"
```

---

## Task 4: Create Supabase Client Utilities

**Files:**
- Create: `web/lib/supabase/client.ts`
- Create: `web/lib/supabase/server.ts`
- Create: `web/.env.local.example`

**Step 1: Create browser client**

```typescript
// web/lib/supabase/client.ts
import { createBrowserClient } from "@supabase/ssr";

export function createClient() {
  return createBrowserClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!
  );
}
```

**Step 2: Create server client**

```typescript
// web/lib/supabase/server.ts
import { createServerClient } from "@supabase/ssr";
import { cookies } from "next/headers";

export async function createClient() {
  const cookieStore = await cookies();

  return createServerClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!,
    {
      cookies: {
        getAll() {
          return cookieStore.getAll();
        },
        setAll(cookiesToSet) {
          try {
            cookiesToSet.forEach(({ name, value, options }) =>
              cookieStore.set(name, value, options)
            );
          } catch {
            // Called from Server Component - can be ignored
          }
        },
      },
    }
  );
}
```

**Step 3: Create env example file**

```bash
# web/.env.local.example
NEXT_PUBLIC_SUPABASE_URL=your-project-url
NEXT_PUBLIC_SUPABASE_ANON_KEY=your-anon-key
```

**Step 4: Commit**

```bash
git add web/lib/ web/.env.local.example
git commit -m "feat: add Supabase client utilities"
```

---

## Task 5: Create Middleware for Session Refresh

**Files:**
- Create: `web/middleware.ts`
- Create: `web/lib/supabase/middleware.ts`

**Step 1: Create middleware utility**

```typescript
// web/lib/supabase/middleware.ts
import { createServerClient } from "@supabase/ssr";
import { NextResponse, type NextRequest } from "next/server";

export async function updateSession(request: NextRequest) {
  let supabaseResponse = NextResponse.next({
    request,
  });

  const supabase = createServerClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!,
    {
      cookies: {
        getAll() {
          return request.cookies.getAll();
        },
        setAll(cookiesToSet) {
          cookiesToSet.forEach(({ name, value }) =>
            request.cookies.set(name, value)
          );
          supabaseResponse = NextResponse.next({
            request,
          });
          cookiesToSet.forEach(({ name, value, options }) =>
            supabaseResponse.cookies.set(name, value, options)
          );
        },
      },
    }
  );

  await supabase.auth.getUser();

  return supabaseResponse;
}
```

**Step 2: Create middleware entry point**

```typescript
// web/middleware.ts
import { type NextRequest } from "next/server";
import { updateSession } from "@/lib/supabase/middleware";

export async function middleware(request: NextRequest) {
  return await updateSession(request);
}

export const config = {
  matcher: [
    "/((?!_next/static|_next/image|favicon.ico|.*\\.(?:svg|png|jpg|jpeg|gif|webp)$).*)",
  ],
};
```

**Step 3: Commit**

```bash
git add web/middleware.ts web/lib/supabase/middleware.ts
git commit -m "feat: add middleware for session refresh"
```

---

## Task 6: Create Login Form Component

**Files:**
- Create: `web/components/login-form.tsx`

**Step 1: Create the login form with phone/OTP steps**

```tsx
// web/components/login-form.tsx
"use client";

import { useState } from "react";
import { createClient } from "@/lib/supabase/client";
import { useRouter } from "next/navigation";

type Step = "phone" | "otp";

export function LoginForm() {
  const [step, setStep] = useState<Step>("phone");
  const [phone, setPhone] = useState("");
  const [otp, setOtp] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const router = useRouter();
  const supabase = createClient();

  const formatPhone = (value: string) => {
    const digits = value.replace(/\D/g, "");
    if (!digits.startsWith("1") && digits.length > 0) {
      return "+1" + digits;
    }
    return "+" + digits;
  };

  const handleSendOtp = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setLoading(true);

    const formattedPhone = formatPhone(phone);

    const { error } = await supabase.auth.signInWithOtp({
      phone: formattedPhone,
    });

    setLoading(false);

    if (error) {
      setError(error.message);
      return;
    }

    setPhone(formattedPhone);
    setStep("otp");
  };

  const handleVerifyOtp = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setLoading(true);

    const { error } = await supabase.auth.verifyOtp({
      phone,
      token: otp,
      type: "sms",
    });

    setLoading(false);

    if (error) {
      setError(error.message);
      return;
    }

    router.push("/dashboard");
  };

  return (
    <div className="w-full max-w-sm">
      <div className="bg-dark-card border border-dark-border rounded-lg p-8">
        <h1 className="text-2xl font-semibold text-center mb-2">CallStack</h1>
        <p className="text-gray-400 text-center text-sm mb-8">
          {step === "phone"
            ? "Enter your phone number to sign in"
            : "Enter the code sent to your phone"}
        </p>

        {step === "phone" ? (
          <form onSubmit={handleSendOtp} className="space-y-4">
            <div>
              <label htmlFor="phone" className="block text-sm text-gray-400 mb-2">
                Phone number
              </label>
              <input
                id="phone"
                type="tel"
                value={phone}
                onChange={(e) => setPhone(e.target.value)}
                placeholder="+1 (555) 000-0000"
                className="w-full px-4 py-3 bg-dark-bg border border-dark-border rounded-md text-white placeholder-gray-500 focus:outline-none focus:border-supabase-green transition-colors"
                required
              />
            </div>

            {error && <p className="text-red-400 text-sm">{error}</p>}

            <button
              type="submit"
              disabled={loading}
              className="w-full py-3 bg-supabase-green text-black font-medium rounded-md hover:bg-supabase-green-dark transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {loading ? "Sending..." : "Send Code"}
            </button>
          </form>
        ) : (
          <form onSubmit={handleVerifyOtp} className="space-y-4">
            <div>
              <label htmlFor="otp" className="block text-sm text-gray-400 mb-2">
                Verification code
              </label>
              <input
                id="otp"
                type="text"
                inputMode="numeric"
                value={otp}
                onChange={(e) => setOtp(e.target.value.replace(/\D/g, ""))}
                placeholder="123456"
                maxLength={6}
                className="w-full px-4 py-3 bg-dark-bg border border-dark-border rounded-md text-white placeholder-gray-500 focus:outline-none focus:border-supabase-green transition-colors text-center text-2xl tracking-widest"
                autoFocus
                required
              />
            </div>

            {error && <p className="text-red-400 text-sm">{error}</p>}

            <button
              type="submit"
              disabled={loading || otp.length !== 6}
              className="w-full py-3 bg-supabase-green text-black font-medium rounded-md hover:bg-supabase-green-dark transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {loading ? "Verifying..." : "Verify"}
            </button>

            <button
              type="button"
              onClick={() => {
                setStep("phone");
                setOtp("");
                setError(null);
              }}
              className="w-full py-2 text-gray-400 text-sm hover:text-white transition-colors"
            >
              Use a different number
            </button>
          </form>
        )}
      </div>
    </div>
  );
}
```

**Step 2: Commit**

```bash
git add web/components/login-form.tsx
git commit -m "feat: add login form component with phone OTP flow"
```

---

## Task 7: Create Login Page

**Files:**
- Create: `web/app/login/page.tsx`

**Step 1: Create the login page**

```tsx
// web/app/login/page.tsx
import { LoginForm } from "@/components/login-form";

export default function LoginPage() {
  return (
    <main className="min-h-screen flex items-center justify-center p-4">
      <LoginForm />
    </main>
  );
}
```

**Step 2: Commit**

```bash
git add web/app/login/
git commit -m "feat: add login page"
```

---

## Task 8: Create Dashboard Page (Placeholder)

**Files:**
- Create: `web/app/dashboard/page.tsx`

**Step 1: Create the dashboard page**

```tsx
// web/app/dashboard/page.tsx
import { redirect } from "next/navigation";
import { createClient } from "@/lib/supabase/server";

export default async function DashboardPage() {
  const supabase = await createClient();
  const { data: { user } } = await supabase.auth.getUser();

  if (!user) {
    redirect("/login");
  }

  return (
    <main className="min-h-screen flex items-center justify-center p-4">
      <div className="bg-dark-card border border-dark-border rounded-lg p-8 max-w-md w-full">
        <h1 className="text-2xl font-semibold mb-4">Dashboard</h1>
        <p className="text-gray-400 mb-4">
          Signed in as: {user.phone}
        </p>
        <form action="/auth/signout" method="post">
          <button
            type="submit"
            className="w-full py-3 bg-dark-border text-white font-medium rounded-md hover:bg-gray-600 transition-colors"
          >
            Sign Out
          </button>
        </form>
      </div>
    </main>
  );
}
```

**Step 2: Commit**

```bash
git add web/app/dashboard/
git commit -m "feat: add protected dashboard page"
```

---

## Task 9: Create Sign Out Route

**Files:**
- Create: `web/app/auth/signout/route.ts`

**Step 1: Create the signout route handler**

```typescript
// web/app/auth/signout/route.ts
import { createClient } from "@/lib/supabase/server";
import { revalidatePath } from "next/cache";
import { type NextRequest, NextResponse } from "next/server";

export async function POST(req: NextRequest) {
  const supabase = await createClient();

  const {
    data: { user },
  } = await supabase.auth.getUser();

  if (user) {
    await supabase.auth.signOut();
  }

  revalidatePath("/", "layout");
  return NextResponse.redirect(new URL("/login", req.url), {
    status: 302,
  });
}
```

**Step 2: Commit**

```bash
git add web/app/auth/
git commit -m "feat: add sign out route handler"
```

---

## Task 10: Update Root Page to Redirect

**Files:**
- Modify: `web/app/page.tsx`

**Step 1: Update root page to redirect to login or dashboard**

```tsx
// web/app/page.tsx
import { redirect } from "next/navigation";
import { createClient } from "@/lib/supabase/server";

export default async function Home() {
  const supabase = await createClient();
  const { data: { user } } = await supabase.auth.getUser();

  if (user) {
    redirect("/dashboard");
  } else {
    redirect("/login");
  }
}
```

**Step 2: Commit**

```bash
git add web/app/page.tsx
git commit -m "feat: add root page redirect logic"
```

---

## Task 11: Update Root Layout

**Files:**
- Modify: `web/app/layout.tsx`

**Step 1: Update layout with dark theme**

```tsx
// web/app/layout.tsx
import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "CallStack",
  description: "Voice-controlled Claude Code orchestration",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body className="antialiased">{children}</body>
    </html>
  );
}
```

**Step 2: Commit**

```bash
git add web/app/layout.tsx
git commit -m "feat: update root layout with metadata"
```

---

## Task 12: Initialize Python Server

**Files:**
- Create: `server/main.py`
- Create: `server/requirements.txt`

**Step 1: Create requirements.txt**

```text
fastapi>=0.109.0
uvicorn[standard]>=0.27.0
python-dotenv>=1.0.0
```

**Step 2: Create main.py**

```python
# server/main.py
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="CallStack API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
async def root():
    return {"status": "ok", "service": "callstack-api"}


@app.get("/health")
async def health():
    return {"status": "healthy"}
```

**Step 3: Commit**

```bash
git add server/
git commit -m "feat: initialize Python FastAPI server"
```

---

## Task 13: Final Verification

**Step 1: Verify frontend starts**

```bash
cd /Users/markshteyn/projects/dispatch/web && npm run dev
```

Expected: Server starts on http://localhost:3000

**Step 2: Verify server starts (in separate terminal)**

```bash
cd /Users/markshteyn/projects/dispatch/server
pip install -r requirements.txt
uvicorn main:app --reload
```

Expected: Server starts on http://localhost:8000

**Step 3: Final commit with all changes**

```bash
git add -A
git commit -m "feat: complete login component with phone OTP auth"
```

---

## Summary

After completing all tasks you will have:

1. **`/web`** - Next.js app with:
   - Phone-based SMS OTP login (`/login`)
   - Protected dashboard (`/dashboard`)
   - Supabase auth integration
   - Dark theme with Supabase green accents

2. **`/server`** - Python FastAPI server with:
   - Basic health check endpoint
   - CORS configured for frontend
   - Ready for orchestrator logic

**To test locally:**
1. Create a Supabase project
2. Enable Phone Auth (Auth → Providers → Phone)
3. Configure Twilio in Supabase dashboard
4. Copy `.env.local.example` to `.env.local` and add your keys
5. Run `npm run dev` in `/web`
