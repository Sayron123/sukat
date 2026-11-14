"use client";

import Link from "next/link";
import { useEffect, useState, type FormEvent } from "react";

import { AuthShell, useHydrated } from "@/components/auth-form";
import { Button, Field, GhostButton, Notice, buttonClass } from "@/components/ui";

const RESEND_WAIT = 30;

const linkClass = "inline-flex min-h-11 items-center self-center text-[15px] font-semibold text-accent-text underline";

export function ForgotForm() {
  const ready = useHydrated();
  const [email, setEmail] = useState("");
  const [sentTo, setSentTo] = useState<string | null>(null);
  const [wait, setWait] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  useEffect(() => {
    if (wait <= 0) return;
    const timer = setTimeout(() => setWait((w) => w - 1), 1000);
    return () => clearTimeout(timer);
  }, [wait]);

  async function send(address: string) {
    setError(null);
    setPending(true);
    try {
      const res = await fetch("/api/auth/forgot-password", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email: address }),
      });
      if (!res.ok) {
        const data = (await res.json().catch(() => null)) as { error?: string } | null;
        setError(data?.error ?? "Something went wrong");
        return;
      }
      setSentTo(address);
      setWait(RESEND_WAIT);
    } catch {
      setError("Network error. Please try again.");
    } finally {
      setPending(false);
    }
  }

  function onSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    void send(email.trim());
  }

  function startOver() {
    setSentTo(null);
    setError(null);
  }

  const errorText = error && (
    <p role="alert" className="text-sm text-red">
      {error}
    </p>
  );

  if (sentTo) {
    return (
      <AuthShell
        title="Check your email"
        subtitle={
          <>
            If <strong className="font-bold text-text">{sentTo}</strong> is a confirmed email on a Sukat account, we
            sent it a link. Open it to make a new password.
          </>
        }
        emote="success"
        back={startOver}
        inlineSubmit
      >
        <div className="flex flex-col gap-3">
          <Notice icon="mail" title="Didn’t get it?" className="border border-border">
            Check your Spam or Promotions folder. The link works for 30 minutes. If you joined by invite and
            never confirmed this email, no link was sent.
          </Notice>
          {errorText}
          <Link href="/login" className={`${buttonClass("primary", "lg")} mt-2`}>
            Back to sign in
          </Link>
          <GhostButton
            type="button"
            onClick={() => void send(sentTo)}
            disabled={wait > 0 || pending}
            className="font-bold"
          >
            {pending ? "Sending…" : wait > 0 ? `Send again in 0:${String(wait).padStart(2, "0")}` : "Send again"}
          </GhostButton>
          <button type="button" onClick={startOver} className={linkClass}>
            Use a different email
          </button>
        </div>
      </AuthShell>
    );
  }

  return (
    <AuthShell
      title="Forgot your password?"
      subtitle="No problem. Enter your email and we’ll send you a link to make a new one."
      back="/login"
      emote="confused"
      inlineSubmit
    >
      <form method="post" onSubmit={onSubmit} className="flex flex-col gap-4">
        <Field
          id="email"
          name="email"
          type="email"
          label="Email"
          autoComplete="email"
          placeholder="you@store.com"
          hint="Use the email you sign in with."
          required
          value={email}
          onChange={(e) => {
            setEmail(e.target.value);
            setError(null);
          }}
        />
        {errorText}
        <Button type="submit" size="lg" disabled={!ready || pending}>
          {pending ? "Please wait…" : "Send link"}
        </Button>
        <Link href="/login" className={linkClass}>
          Back to sign in
        </Link>
      </form>
      <p className="mt-auto pt-10 text-center text-[13px] leading-relaxed text-muted">
        Staff member? Use the email from your invite.
      </p>
    </AuthShell>
  );
}
