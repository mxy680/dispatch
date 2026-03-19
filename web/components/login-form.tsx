"use client";

import { useState } from "react";
import { createClient } from "@/lib/supabase/client";
import { useRouter } from "next/navigation";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";

type Step = "phone" | "otp";

export function LoginForm() {
  const [step, setStep] = useState<Step>("phone");
  const [phone, setPhone] = useState("");
  const [otp, setOtp] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const router = useRouter();
  const supabase = createClient();

  const handleGoogleSignIn = async () => {
    setError(null);
    setLoading(true);
    const { error } = await supabase.auth.signInWithOAuth({
      provider: "google",
      options: {
        redirectTo: `${window.location.origin}/auth/callback`,
      },
    });
    if (error) {
      setError(error.message);
      setLoading(false);
    }
  };

// for testing skip the formating for now
  // const formatPhone = (value: string) => {
  //   const digits = value.replace(/\D/g, "");
  //   if (!digits.startsWith("1") && digits.length > 0) {
  //     return "+1" + digits;
  //   }
  //   return "+" + digits;
  // };

  const formatPhone = (value: string) => {
    const digits = value.replace(/\D/g, "");
return digits
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

    const { data, error } = await supabase.auth.verifyOtp({
      phone, // Ensure this still has the "+" if needed
      token: otp,
      type: "sms",
    });

    if (error) {
      setLoading(false);
      setError(error.message);
      return;
    }

    if (data.session) {
      // 1. Sync server-side state with the new cookie
      router.refresh();

      // 2. Use a slight delay to let the refresh complete
      setTimeout(() => {
        router.push("/dashboard");
      }, 150);
    }
  };

  return (
    <div className="w-full max-w-sm">
      <Card className="bg-dark-card border-dark-border">
        <CardHeader className="pb-0">
          <h1 className="text-2xl font-semibold text-center mb-2">Dispatch</h1>
          <p className="text-gray-400 text-center text-sm mb-2">
            {step === "phone"
              ? "Sign in to continue"
              : "Enter the code sent to your phone"}
          </p>
        </CardHeader>
        <CardContent className="pt-6">
          <Button
            type="button"
            variant="outline"
            onClick={handleGoogleSignIn}
            disabled={loading}
            className="w-full bg-white text-black hover:bg-gray-100 hover:text-black border-0"
          >
            <svg className="w-5 h-5" viewBox="0 0 24 24">
              <path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92a5.06 5.06 0 0 1-2.2 3.32v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.1z" />
              <path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" />
              <path fill="#FBBC05" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z" />
              <path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z" />
            </svg>
            Sign in with Google
          </Button>

          <div className="flex items-center gap-4 my-4">
            <div className="flex-1 h-px bg-dark-border" />
            <span className="text-gray-500 text-sm">or</span>
            <div className="flex-1 h-px bg-dark-border" />
          </div>

          {step === "phone" ? (
            <form onSubmit={handleSendOtp} className="space-y-4">
              <div>
                <Label htmlFor="phone" className="text-gray-400 mb-2 block">
                  Phone number
                </Label>
                <Input
                  id="phone"
                  type="tel"
                  value={phone}
                  onChange={(e) => setPhone(e.target.value)}
                  placeholder="+1 (555) 000-0000"
                  className="bg-dark-bg border-dark-border text-white placeholder:text-gray-500 focus-visible:ring-0 focus-visible:border-supabase-green"
                  required
                />
              </div>

              {error && <p className="text-red-400 text-sm">{error}</p>}

              <Button
                type="submit"
                disabled={loading}
                className="w-full bg-supabase-green text-black font-medium hover:bg-supabase-green-dark"
              >
                {loading ? "Sending..." : "Send Code"}
              </Button>
            </form>
          ) : (
            <form onSubmit={handleVerifyOtp} className="space-y-4">
              <div>
                <Label htmlFor="otp" className="text-gray-400 mb-2 block">
                  Verification code
                </Label>
                <Input
                  id="otp"
                  type="text"
                  inputMode="numeric"
                  value={otp}
                  onChange={(e) => setOtp(e.target.value.replace(/\D/g, ""))}
                  placeholder="123456"
                  maxLength={6}
                  className="bg-dark-bg border-dark-border text-white placeholder:text-gray-500 focus-visible:ring-0 focus-visible:border-supabase-green text-center text-2xl tracking-widest"
                  autoFocus
                  required
                />
              </div>

              {error && <p className="text-red-400 text-sm">{error}</p>}

              <Button
                type="submit"
                disabled={loading || otp.length !== 6}
                className="w-full bg-supabase-green text-black font-medium hover:bg-supabase-green-dark"
              >
                {loading ? "Verifying..." : "Verify"}
              </Button>

              <Button
                type="button"
                variant="ghost"
                onClick={() => {
                  setStep("phone");
                  setOtp("");
                  setError(null);
                }}
                className="w-full text-gray-400 text-sm hover:text-white"
              >
                Use a different number
              </Button>
            </form>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
