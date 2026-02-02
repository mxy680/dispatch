# Login Component Design

Phone-based SMS OTP authentication for CallStack using Supabase and Next.js.

## Project Structure

```
dispatch/
├── web/                    # Next.js frontend
│   ├── app/
│   │   ├── layout.tsx      # Root layout with dark theme
│   │   ├── page.tsx        # Redirects to /login or /dashboard
│   │   ├── login/
│   │   │   └── page.tsx    # Login page
│   │   └── dashboard/
│   │       └── page.tsx    # Protected dashboard (placeholder)
│   ├── components/
│   │   └── login-form.tsx  # Login form component
│   ├── lib/
│   │   └── supabase.ts     # Supabase client setup
│   ├── package.json
│   └── tailwind.config.ts
│
├── server/                 # Python FastAPI backend
│   ├── main.py             # Entry point
│   └── requirements.txt
│
└── README.md
```

## Login Component

### Visual Design

- Dark background (#1a1a1a)
- Supabase green accent (#3ECF8E) for buttons and focus states
- Centered card with subtle border
- Minimal: phone input, one button, small helper text

### Flow States

1. **Phone entry** — Input with country code (+1 default), "Send Code" button
2. **Code entry** — 6-digit input, "Verify" button, "Back" link
3. **Loading** — Button spinner during API calls
4. **Error** — Inline red text below input

### Behavior

- Phone number validated before sending
- Auto-focus on code input after SMS sent
- Redirect to /dashboard on success
- Session managed by Supabase client

## Supabase Auth Integration

### Setup Required

1. Enable Phone Auth in Supabase dashboard (Authentication → Providers → Phone)
2. Configure Twilio credentials in Supabase for SMS delivery

### Auth Flow

```
User enters phone → supabase.auth.signInWithOtp({ phone })
                  → Supabase sends SMS via Twilio
User enters code  → supabase.auth.verifyOtp({ phone, token, type: 'sms' })
                  → Session returned, redirect to dashboard
```

### Environment Variables

```
NEXT_PUBLIC_SUPABASE_URL=<project-url>
NEXT_PUBLIC_SUPABASE_ANON_KEY=<anon-key>
```

## Python Server Connection

- Server uses Supabase service role key to verify JWTs
- Frontend sends access token in Authorization header
- Server validates token before processing requests

## Tech Stack

- **Frontend**: Next.js 14+ (App Router), Tailwind CSS, @supabase/ssr
- **Backend**: Python, FastAPI
- **Auth**: Supabase Phone Auth + Twilio SMS
