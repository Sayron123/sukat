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
  subtitle: string;
  back?: string;
  mascot?: number;
  emote?: Emote;
  inlineSubmit?: boolean;
  children: ReactNode;
}) {
  const top = mascot ? (back ? "pt-14" : "pt-8") : back ? "pt-20" : "pt-16";
  return (
    <main className={`relative mx-auto w-full max-w-lg flex-1 px-6 ${inlineSubmit ? "pb-10" : "pb-36"} ${top}`}>
      {back && (
        <Link
          href={back}
          className="absolute top-4 left-6 -ml-2 flex h-11 items-center gap-1.5 rounded-button px-2 text-[15px] font-semibold text-text hover:bg-surface"
        >
          <Icon name="arrow" />
          Back
        </Link>
      )}
      {mascot ? (
        <div className="mb-7 flex flex-col items-center text-center">
          <Mascot emote={emote} size={mascot} glow alt="" />
          <h1
            className={`mt-2 leading-tight font-extrabold tracking-tight text-text ${
              mascot >= 140 ? "text-[40px]" : "text-[32px]"
            }`}
          >
            Sukat
          </h1>
          <p className="mt-1.5 text-sm text-muted">{subtitle}</p>
        </div>
      ) : (
        <>
          <div
            aria-hidden
            className="mb-[30px] grid h-[52px] w-[52px] place-items-center rounded-button bg-text text-base font-bold text-inverse"
          >
            S
          </div>
          <p className="text-[13px] font-bold text-muted uppercase">Sukat</p>
          <h1 className="mt-1 text-[28px] leading-tight font-bold text-text">{title}</h1>
          <p className="mt-2 mb-7 text-sm text-muted">{subtitle}</p>
        </>
      )}
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
  note,
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
  note?: string;
}) {
  const sections = [...new Set(fields.flatMap((f) => (f.section ? [f.section] : [])))];
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);
  const [finished, setFinished] = useState(false);
  // Keep submit disabled until JavaScript has loaded, so the browser never falls back to a
  // plain form submit. (method="post" below also keeps fields out of the URL either way.)
  // false during server render and before hydration, true once the page is interactive.
  const ready = useSyncExternalStore(
    noopSubscribe,
    () => true,
    () => false,
  );
  const signedOut =
    useSyncExternalStore(
      noopSubscribe,
      () => new URLSearchParams(window.location.search).has("expired"),
      () => false,
    ) && signedOutText !== undefined;

  async function onSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setError(null);
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
      if (newPassword && typeof body.email === "string") {
        await offerToSavePassword(body.email, String(body[newPassword]));
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

  return (
    <AuthShell
      title={title}
      subtitle={signedOut && signedOutText ? signedOutText : subtitle}
      back={back}
      mascot={mascot}
      emote={signedOut ? "sleeping" : "normal"}
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
          {footer && footer.href !== back && (
            <Link href={footer.href} className={`${textLinkClass} self-start`}>
              {footer.text}
            </Link>
          )}
          {createAccount ? (
            <>
              <Button type="submit" size="lg" disabled={!ready || pending} className="-mt-2">
                {pending ? "Please wait…" : submitLabel}
              </Button>
              <div className="-my-1 flex items-center gap-3 text-[13px] text-muted">
                <span aria-hidden className="h-px flex-1 bg-border" />
                {createAccount.prompt}
                <span aria-hidden className="h-px flex-1 bg-border" />
              </div>
              <Link href={createAccount.href} className="flex h-12 items-center justify-center rounded-button border border-line bg-surface px-4 text-[15px] font-bold text-text hover:bg-background">
                {createAccount.text}
              </Link>
            </>
          ) : (
            <div className="fixed inset-x-0 bottom-0 border-t border-border bg-background">
              <div className="mx-auto max-w-lg px-6 pt-3 pb-6">
                <Button type="submit" size="lg" disabled={!ready || pending}>
                  {pending ? "Please wait…" : submitLabel}
                </Button>
              </div>
            </div>
          )}
        </form>
      )}
      {note && !finished && <p className="mt-16 text-center text-[13px] leading-relaxed text-muted">{note}</p>}
    </AuthShell>
  );
}
