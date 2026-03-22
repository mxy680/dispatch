"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { authFetch } from "@/lib/supabase/access-token";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

type Step = "phone_input" | "otp_input";

interface Props {
  open: boolean;
}

const BACKEND_URL =
  process.env.NEXT_PUBLIC_BACKEND_URL ?? "http://localhost:8000";

function maskPhone(phone: string): string {
  // Show last 4 digits: +1 (***) ***-XXXX
  if (phone.length >= 4) {
    return "***-***-" + phone.slice(-4);
  }
  return phone;
}

function normalizePhone(raw: string): string {
  const digits = raw.replace(/\D/g, "");
  if (digits.length === 10) {
    return "+1" + digits;
  }
  if (digits.length === 11 && digits.startsWith("1")) {
    return "+" + digits;
  }
  // If already has + prefix, return as-is
  if (raw.startsWith("+")) return raw.trim();
  return raw.trim();
}

export function PhoneOnboardingDialog({ open }: Props) {
  const router = useRouter();
  const [step, setStep] = useState<Step>("phone_input");
  const [phoneInput, setPhoneInput] = useState("");
  const [normalizedPhone, setNormalizedPhone] = useState("");
  const [codeInput, setCodeInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSendCode(e: React.FormEvent) {
    e.preventDefault();
    setError(null);

    const phone = normalizePhone(phoneInput);
    const e164 = /^\+[1-9]\d{1,14}$/.test(phone);
    if (!e164) {
      setError("Enter a valid US phone number (10 digits) or E.164 format.");
      return;
    }

    setLoading(true);
    try {
      const res = await authFetch(`${BACKEND_URL}/api/phone/send-otp`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ phone_number: phone }),
      });
      const data = await res.json();
      if (!res.ok || !data.success) {
        setError(data.detail ?? data.error ?? "Failed to send code. Try again.");
        return;
      }
      setNormalizedPhone(phone);
      setStep("otp_input");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Network error. Try again.");
    } finally {
      setLoading(false);
    }
  }

  async function handleVerifyCode(e: React.FormEvent) {
    e.preventDefault();
    setError(null);

    if (!/^\d{6}$/.test(codeInput)) {
      setError("Enter the 6-digit code from your SMS.");
      return;
    }

    setLoading(true);
    try {
      const res = await authFetch(`${BACKEND_URL}/api/phone/verify-otp`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ phone_number: normalizedPhone, code: codeInput }),
      });
      const data = await res.json();
      if (!res.ok || !data.success) {
        setError(data.error ?? data.detail ?? "Verification failed. Check the code and try again.");
        return;
      }
      router.refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Network error. Try again.");
    } finally {
      setLoading(false);
    }
  }

  async function handleResend() {
    setError(null);
    setLoading(true);
    try {
      const res = await authFetch(`${BACKEND_URL}/api/phone/send-otp`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ phone_number: normalizedPhone }),
      });
      const data = await res.json();
      if (!res.ok || !data.success) {
        setError(data.detail ?? data.error ?? "Failed to resend code.");
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Network error. Try again.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <Dialog open={open}>
      <DialogContent
        onPointerDownOutside={(e) => e.preventDefault()}
        onEscapeKeyDown={(e) => e.preventDefault()}
        showCloseButton={false}
        className="sm:max-w-md"
      >
        {step === "phone_input" && (
          <>
            <DialogHeader>
              <DialogTitle>Verify your phone number</DialogTitle>
              <DialogDescription>
                We'll send a one-time code to your mobile number to verify your account.
              </DialogDescription>
            </DialogHeader>
            <form onSubmit={handleSendCode} className="space-y-4 pt-2">
              <div className="space-y-1">
                <Label htmlFor="phone">Phone number</Label>
                <Input
                  id="phone"
                  type="tel"
                  placeholder="+1 (555) 000-0000"
                  value={phoneInput}
                  onChange={(e) => setPhoneInput(e.target.value)}
                  disabled={loading}
                  autoFocus
                />
              </div>
              {error && (
                <p className="text-sm text-destructive">{error}</p>
              )}
              <Button type="submit" className="w-full" disabled={loading}>
                {loading ? "Sending..." : "Send Code"}
              </Button>
            </form>
          </>
        )}

        {step === "otp_input" && (
          <>
            <DialogHeader>
              <DialogTitle>Enter your verification code</DialogTitle>
              <DialogDescription>
                We sent a 6-digit code to {maskPhone(normalizedPhone)}.
              </DialogDescription>
            </DialogHeader>
            <form onSubmit={handleVerifyCode} className="space-y-4 pt-2">
              <div className="space-y-1">
                <Label htmlFor="code">Verification code</Label>
                <Input
                  id="code"
                  type="text"
                  inputMode="numeric"
                  placeholder="123456"
                  maxLength={6}
                  value={codeInput}
                  onChange={(e) => setCodeInput(e.target.value.replace(/\D/g, ""))}
                  disabled={loading}
                  autoFocus
                />
              </div>
              {error && (
                <p className="text-sm text-destructive">{error}</p>
              )}
              <Button type="submit" className="w-full" disabled={loading}>
                {loading ? "Verifying..." : "Verify"}
              </Button>
              <p className="text-center text-sm text-muted-foreground">
                Didn't receive it?{" "}
                <Button
                  type="button"
                  variant="link"
                  size="sm"
                  className="h-auto p-0 underline hover:no-underline"
                  onClick={handleResend}
                  disabled={loading}
                >
                  Resend Code
                </Button>
              </p>
            </form>
          </>
        )}
      </DialogContent>
    </Dialog>
  );
}
