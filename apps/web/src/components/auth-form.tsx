"use client";
import { useState } from "react";
import { useRouter } from "next/navigation";
import { ArrowRight, Eye, EyeOff, LoaderCircle } from "lucide-react";
import { authClient } from "@/lib/auth-client";
import { signInInput, signUpInput } from "@/lib/auth-input";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

export function AuthForm({ googleEnabled }: { googleEnabled: boolean }) {
  const router = useRouter();
  const [mode, setMode] = useState<"signin" | "signup">("signin");
  const [visible, setVisible] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault(); setError("");
    const form = new FormData(event.currentTarget);
    const input = { email: String(form.get("email") ?? "").trim(), password: String(form.get("password") ?? ""), name: String(form.get("name") ?? "") };
    const parsed = (mode === "signup" ? signUpInput : signInInput).safeParse(input);
    if (!parsed.success) { setError(parsed.error.issues[0].message); return; }
    setBusy(true);
    try {
      const result = mode === "signup"
        ? await authClient.signUp.email({ ...parsed.data, name: input.name.trim() })
        : await authClient.signIn.email(parsed.data);
      if (result.error) {
        setError(result.error.status === 429 ? "Too many attempts. Please wait a minute and try again." : mode === "signin" ? "We couldn’t sign you in. Check your email and password." : "We couldn’t create this account. Try signing in if you already have one.");
        return;
      }
      router.push("/workspace"); router.refresh();
    } catch { setError("Unable to connect. Please try again."); }
    finally { setBusy(false); }
  }

  async function google() {
    setBusy(true); setError("");
    try {
      const result = await authClient.signIn.social({ provider: "google", callbackURL: "/workspace" });
      if (result.error) { setError("Google sign-in couldn’t start. Please try again."); setBusy(false); }
    } catch { setError("Unable to connect to Google sign-in."); setBusy(false); }
  }

  return <div className="auth-form-wrap">
    <span className="eyebrow">YOUR PERSONAL MONEY WORKSPACE</span>
    <h2>{mode === "signin" ? "Good to see you." : "Let’s make a little room."}</h2>
    <p className="form-intro">{mode === "signin" ? "Sign in to pick up where you left off." : "Create an account for your next 30 days."}</p>
    {googleEnabled && <><Button variant="outline" className="google-button" disabled={busy} onClick={google}><span aria-hidden="true" className="google-letter">G</span> Continue with Google</Button><div className="auth-divider"><span>or continue with email</span></div></>}
    <form onSubmit={submit} className="auth-form" noValidate>
      <fieldset disabled={busy}>
        {mode === "signup" && <div className="field"><Label htmlFor="name">Your name</Label><Input id="name" name="name" autoComplete="name" placeholder="How should we call you?" maxLength={80} required /></div>}
        <div className="field"><Label htmlFor="email">Email address</Label><Input id="email" name="email" type="email" autoComplete="email" placeholder="you@example.com" maxLength={254} required /></div>
        <div className="field"><Label htmlFor="password">Password</Label><div className="password-field"><Input id="password" name="password" type={visible ? "text" : "password"} autoComplete={mode === "signup" ? "new-password" : "current-password"} placeholder={mode === "signup" ? "At least 12 characters" : "Enter your password"} maxLength={128} required aria-describedby={error ? "auth-error" : undefined} /><button className="password-toggle" type="button" onClick={() => setVisible(!visible)} aria-label={visible ? "Hide password" : "Show password"}>{visible ? <EyeOff size={18} /> : <Eye size={18} />}</button></div></div>
        {error && <p role="alert" id="auth-error" className="form-error">{error}</p>}
        <Button type="submit" className="auth-submit">{busy ? <><LoaderCircle className="animate-spin" size={18} /> Please wait</> : <>{mode === "signin" ? "Sign in" : "Create account"}<ArrowRight size={18} /></>}</Button>
      </fieldset>
    </form>
    <p className="auth-switch">{mode === "signin" ? "New to Riverline?" : "Already have an account?"} <button type="button" disabled={busy} onClick={() => { setMode(mode === "signin" ? "signup" : "signin"); setError(""); }}>{mode === "signin" ? "Create an account" : "Sign in"}</button></p>
    <div className="auth-note">Your plan stays in your account.<br />You decide what to share and what to change.</div>
  </div>;
}
