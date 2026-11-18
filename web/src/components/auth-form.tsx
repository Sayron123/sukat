"use client";

import Link from "next/link";
import { Fragment, useState, useSyncExternalStore, type FormEvent, type ReactNode } from "react";

import { hardNavigate } from "@/lib/hard-navigate";
import { WEAK_PASSWORD, offerToSavePassword, passwordIsStrong } from "@/lib/password";
import { clearSessionData } from "@/lib/session-data";

import { Icon } from "./icons";
import { Mascot, type Emote } from "./mascot";
import { NewPasswordFields } from "./new-password-fields";
import { PasswordField } from "./password-field";
import { Button, Field, Notice, textLinkClass } from "./ui";

const noopSubscribe = () => () => {};

type FieldDef = {
  name: string;
  label: string;
  type?: string;
  autoComplete?: string;
  minLength?: number;
  maxLength?: number;
  optional?: boolean;
  locked?: string;
  placeholder?: string;
  hint?: string;
  section?: string;
};

function SectionTitle({ number, title, first }: { number: number; title: string; first: boolean }) {
  return (
    <h2 className={`flex items-center gap-2.5 text-base font-extrabold text-text ${first ? "" : "mt-2"}`}>
      <span
        aria-hidden
        className="grid h-6 w-6 shrink-0 place-items-center rounded-full bg-accent text-[13px] font-extrabold text-white"
      >
        {number}
      </span>
      {title}
    </h2>
  );
}

export function useHydrated() {
  return useSyncExternalStore(
    noopSubscribe,
    () => true,
    () => false,
  );
}

const backClass =
  "absolute top-4 left-6 -ml-2 flex h-11 items-center gap-1.5 rounded-button px-2 text-[15px] font-semibold text-text hover:bg-surface";

export function AuthShell({
  title,
  subtitle,
  back,
  mascot,
  emote = "normal",
  inlineSubmit = false,
  children,
}: {
  title: string;
  subtitle: ReactNode;
  back?: string | (() => void);
  mascot?: number;
  emote?: Emote;
  inlineSubmit?: boolean;
  children: ReactNode;
}) {
  return (
    <main
      className={`relative mx-auto flex w-full max-w-lg flex-1 flex-col px-6 ${inlineSubmit ? "pb-10" : "pb-36"} ${
        back ? "pt-14" : "pt-8"
      }`}
    >
      {typeof back === "string" && (
        <Link href={back} className={backClass}>
          <Icon name="arrow" />
          Back
        </Link>
      )}
      {typeof back === "function" && (
        <button type="button" onClick={back} className={backClass}>
          <Icon name="arrow" />
          Back
        </button>
      )}
      <div className="mb-7 flex flex-col items-center text-center">
        <Mascot emote={emote} size={mascot ?? 120} glow alt="" />
        {mascot ? (
          <>
            <h1
              className={`mt-2 leading-tight font-extrabold tracking-tight text-text ${
                mascot >= 140 ? "text-[40px]" : "text-[32px]"
              }`}
            >
              Sukat
            </h1>
            <p className="mt-1.5 text-sm text-muted">{subtitle}</p>
          </>
        ) : (
          <>
            <h1 className="mt-3 text-[28px] leading-8.5 font-extrabold tracking-tight text-text">{title}</h1>
            <p className="mt-2 max-w-[320px] text-[15px] leading-5.5 text-muted">{subtitle}</p>
          </>
        )}
      </div>
      {children}
    </main>
  );
}

export function AuthForm({
  title,
  subtitle,
  endpoint,
  fields,
  submitLabel,
  footer,
  back,
  altLink,
  extra,
  done,
  agreement = false,
  mascot,
  signedOutText,
  createAccount,
  google,
  alert,
}: {
  title: string;
  subtitle: string;
  endpoint: string;
  fields: FieldDef[];
  submitLabel: string;
  footer?: { text: string; href: string };
  back?: string;
  altLink?: { text: string; href: string };
  extra?: Record<string, string>;
  done?: string;
  agreement?: boolean;
  mascot?: number;
  signedOutText?: string;
  createAccount?: { prompt: string; text: string; href: string };
  google?: { mode: "login" | "signup" | "invite"; token?: string };
  alert?: string;
}) {
  const sections = [...new Set(fields.flatMap((f) => (f.section ? [f.section] : [])))];
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);
  const [finished, setFinished] = useState(false);
  // Keep submit disabled until JavaScript has loaded, so the browser never falls back to a
  // plain form submit. (method="post" below also keeps fields out of the URL either way.)
  // false during server render and before hydration, true once the page is interactive.
  const ready = useHydrated();
  const signedOut =
    useSyncExternalStore(
      noopSubscribe,
      () => new URLSearchParams(window.location.search).has("expired"),
      () => false,
    ) && signedOutText !== undefined;

  function startGoogle(form: HTMLFormElement) {
    if (!google) return;
    const data = new FormData(form);
    if (agreement && data.get("accept_terms") !== "on") {
      setError("Please agree to the Terms and Privacy Policy first.");
      return;
    }
    if (google.mode === "signup" && !String(data.get("store_name") ?? "").trim()) {
      setError("Type your store name first.");
      return;
    }
    const values: Record<string, string | undefined> = {
      mode: google.mode,
      token: google.token,
      store_name: String(data.get("store_name") ?? "") || undefined,
      store_address: String(data.get("store_address") ?? "") || undefined,
    };
    const out = document.createElement("form");
    out.method = "post";
    out.action = "/api/auth/google/start";
    for (const [name, value] of Object.entries(values)) {
      if (value === undefined) continue;
      const input = document.createElement("input");
      input.type = "hidden";
      input.name = name;
      input.value = value;
      out.appendChild(input);
    }
    document.body.appendChild(out);
    setPending(true);
    out.submit();
  }

  async function onSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setError(null);
    const submitter = (e.nativeEvent as SubmitEvent).submitter;
    if (submitter instanceof HTMLButtonElement && submitter.name === "google") {
      startGoogle(e.currentTarget);
      return;
    }
    const body: Record<string, unknown> = {
      ...Object.fromEntries(new FormData(e.currentTarget)),
      ...extra,
    };
    if (agreement) body.accept_terms = body.accept_terms === "on";
    const newPassword = fields.find((f) => f.type === "new-password")?.name;
    if (newPassword) {
      if (!passwordIsStrong(String(body[newPassword]))) {
        setError(WEAK_PASSWORD);
        return;
      }
      if (body[newPassword] !== body.confirm_password) {
        setError("The passwords do not match");
        return;
      }
      delete body.confirm_password;
    }
    setPending(true);
    try {
      const res = await fetch(endpoint, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      if (!res.ok) {
        const data = (await res.json().catch(() => null)) as { error?: string } | null;
        setError(data?.error ?? "Something went wrong");
        return;
      }
      if (done) {
        setFinished(true);
        return;
      }
      const account = body.username ?? body.email;
      if (newPassword && typeof account === "string") {
        await offerToSavePassword(account, String(body[newPassword]));
      }
      // Also covers a previous person who never signed out (e.g. their session expired).
      clearSessionData();
      hardNavigate("/");
    } catch {
      setError("Network error. Please try again.");
    } finally {
      setPending(false);
    }
  }

  const googleOption = google && (
    <>
      <div className="-my-1 flex items-center gap-3 text-[13px] text-muted">
        <span aria-hidden className="h-px flex-1 bg-border" />
        or
        <span aria-hidden className="h-px flex-1 bg-border" />
      </div>
      <button
        type="submit"
        name="google"
        value="1"
        formNoValidate
        disabled={!ready || pending}
        className="flex h-12 items-center justify-center gap-2.5 rounded-button border border-line bg-surface px-4 text-[15px] font-bold text-text hover:bg-background disabled:opacity-45"
      >
        <GoogleMark />
        Continue with Google
      </button>
    </>
  );

  return (
    <AuthShell
      title={title}
      subtitle={signedOut && signedOutText ? signedOutText : subtitle}
      back={back}
      mascot={mascot}
      emote={finished ? "success" : signedOut ? "sleeping" : "normal"}
      inlineSubmit={createAccount !== undefined}
    >
      {finished ? (
        <>
          <Notice title="Done">{done}</Notice>
          {footer && (
            <Link href={footer.href} className={`${textLinkClass} mt-3`}>
              {footer.text}
            </Link>
          )}
        </>
      ) : (
        <form method="post" onSubmit={onSubmit} onChange={() => setError(null)} className="flex flex-col gap-[22px]">
          {alert && (
            <p role="alert" className="rounded-button border border-red-edge bg-red-soft p-3 text-sm text-red">
              {alert}
            </p>
          )}
          {fields.map((f, i) => {
            const startsSection = f.section !== undefined && f.section !== fields[i - 1]?.section;
            let input: ReactNode;
            if (f.type === "new-password") {
              input = <NewPasswordFields name={f.name} label={f.label} onSuggest={() => setError(null)} />;
            } else {
              const locked = f.locked
                ? { defaultValue: f.locked, readOnly: true, hint: "This comes from your invite." }
                : {};
              const shared = {
                id: f.name,
                name: f.name,
                label: f.label,
                autoComplete: f.autoComplete,
                minLength: f.minLength,
                maxLength: f.maxLength,
                required: !f.optional,
                placeholder: f.placeholder,
                hint: f.hint,
                ...locked,
              };
              input =
                f.type === "password" ? <PasswordField {...shared} /> : <Field type={f.type ?? "text"} {...shared} />;
            }
            return (
              <Fragment key={f.name}>
                {startsSection && f.section && (
                  <SectionTitle number={sections.indexOf(f.section) + 1} title={f.section} first={i === 0} />
                )}
                {input}
              </Fragment>
            );
          })}
          {altLink && (
            <Link
              href={altLink.href}
              className={
                createAccount
                  ? "-mt-4 inline-flex min-h-11 items-center self-start text-[13px] font-semibold text-accent-text underline"
                  : `${textLinkClass} -mt-4 self-start`
              }
            >
              {altLink.text}
            </Link>
          )}
          {agreement && (
            <label htmlFor="accept_terms" className="flex items-start gap-3 text-sm text-text">
              <input
                id="accept_terms"
                name="accept_terms"
                type="checkbox"
                required
                className="mt-0.5 h-5 w-5 shrink-0 accent-text"
              />
              <span>
                I agree to the{" "}
                <Link href="/terms" target="_blank" className="underline">
                  Terms
                </Link>{" "}
                and{" "}
                <Link href="/privacy" target="_blank" className="underline">
                  Privacy Policy
                </Link>
                .
              </span>
            </label>
          )}
          {error && (
            <p role="alert" className="text-sm text-red">
              {error}
            </p>
          )}
          {!createAccount && (
            <>
              <div className="fixed inset-x-0 bottom-0 border-t border-border bg-background">
                <div className="mx-auto max-w-lg px-6 pt-3 pb-6">
                  <Button type="submit" size="lg" disabled={!ready || pending}>
                    {pending ? "Please wait…" : submitLabel}
                  </Button>
                </div>
              </div>
              {googleOption}
            </>
          )}
          {footer && footer.href !== back && (
            <Link href={footer.href} className={`${textLinkClass} self-start`}>
              {footer.text}
            </Link>
          )}
          {createAccount && (
            <>
              <Button type="submit" size="lg" disabled={!ready || pending} className="-mt-2">
                {pending ? "Please wait…" : submitLabel}
              </Button>
              {googleOption}
              <div className="-my-1 flex items-center gap-3 text-[13px] text-muted">
                <span aria-hidden className="h-px flex-1 bg-border" />
                {createAccount.prompt}
                <span aria-hidden className="h-px flex-1 bg-border" />
              </div>
              <Link href={createAccount.href} className="flex h-12 items-center justify-center rounded-button border border-line bg-surface px-4 text-[15px] font-bold text-text hover:bg-background">
                {createAccount.text}
              </Link>
            </>
          )}
        </form>
      )}
    </AuthShell>
  );
}

function GoogleMark() {
  return (
    <svg width="20" height="20" viewBox="0 0 48 48" aria-hidden="true">
      <path fill="#FFC107" d="M43.6 20.5H42V20H24v8h11.3C33.7 32.7 29.2 36 24 36c-6.6 0-12-5.4-12-12s5.4-12 12-12c3.1 0 5.8 1.2 7.9 3l5.7-5.7C34 6.1 29.3 4 24 4 12.9 4 4 12.9 4 24s8.9 20 20 20 20-8.9 20-20c0-1.3-.1-2.4-.4-3.5z" />
      <path fill="#FF3D00" d="m6.3 14.7 6.6 4.8C14.7 15.1 19 12 24 12c3.1 0 5.8 1.2 7.9 3l5.7-5.7C34 6.1 29.3 4 24 4 16.3 4 9.7 8.3 6.3 14.7z" />
      <path fill="#4CAF50" d="M24 44c5.2 0 9.9-2 13.4-5.2l-6.2-5.2C29.2 35.1 26.7 36 24 36c-5.2 0-9.6-3.3-11.3-8l-6.5 5C9.5 39.6 16.2 44 24 44z" />
      <path fill="#1976D2" d="M43.6 20.5H42V20H24v8h11.3c-.8 2.2-2.2 4.2-4.1 5.6l6.2 5.2C37 39.2 44 34 44 24c0-1.3-.1-2.4-.4-3.5z" />
    </svg>
  );
}
