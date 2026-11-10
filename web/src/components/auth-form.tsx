"use client";

import Link from "next/link";
import { useState, useSyncExternalStore, type FormEvent, type ReactNode } from "react";

import { hardNavigate } from "@/lib/hard-navigate";
import { WEAK_PASSWORD, offerToSavePassword, passwordIsStrong } from "@/lib/password";
import { clearSessionData } from "@/lib/session-data";

import { Icon } from "./icons";
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
};

export function AuthShell({
  title,
  subtitle,
  back,
  children,
}: {
  title: string;
  subtitle: string;
  back?: string;
  children: ReactNode;
}) {
  return (
    <main className={`relative mx-auto w-full max-w-lg flex-1 px-6 pb-36 ${back ? "pt-20" : "pt-16"}`}>
      {back && (
        <Link
          href={back}
          className="absolute top-4 left-6 -ml-2 flex h-11 items-center gap-1.5 rounded-button px-2 text-[15px] font-semibold text-text hover:bg-surface"
        >
          <Icon name="arrow" />
          Back
        </Link>
      )}
      <div
        aria-hidden
        className="mb-[30px] grid h-[52px] w-[52px] place-items-center rounded-button bg-text text-base font-bold text-white"
      >
        S
      </div>
      <p className="text-[13px] font-bold text-muted uppercase">Sukat</p>
      <h1 className="mt-1 text-[28px] leading-tight font-bold text-text">{title}</h1>
      <p className="mt-2 mb-7 text-sm text-muted">{subtitle}</p>
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
}: {
  title: string;
  subtitle: string;
  endpoint: string;
  fields: FieldDef[];
  submitLabel: string;
  footer: { text: string; href: string };
  back?: string;
  altLink?: { text: string; href: string };
  extra?: Record<string, string>;
  done?: string;
}) {
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

  async function onSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setError(null);
    const body: Record<string, unknown> = {
      ...Object.fromEntries(new FormData(e.currentTarget)),
      ...extra,
    };
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
    <AuthShell title={title} subtitle={subtitle} back={back}>
      {finished ? (
        <>
          <Notice title="Done">{done}</Notice>
          <Link href={footer.href} className={`${textLinkClass} mt-3`}>
            {footer.text}
          </Link>
        </>
      ) : (
        <form method="post" onSubmit={onSubmit} onChange={() => setError(null)} className="flex flex-col gap-[22px]">
          {fields.map((f) => {
            if (f.type === "new-password") {
              return <NewPasswordFields key={f.name} name={f.name} label={f.label} onSuggest={() => setError(null)} />;
            }
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
              ...locked,
            };
            return f.type === "password" ? (
              <PasswordField key={f.name} {...shared} />
            ) : (
              <Field key={f.name} type={f.type ?? "text"} {...shared} />
            );
          })}
          {altLink && (
            <Link href={altLink.href} className={`${textLinkClass} -mt-4 self-start`}>
              {altLink.text}
            </Link>
          )}
          {error && (
            <p role="alert" className="text-sm text-red">
              {error}
            </p>
          )}
          {footer.href !== back && (
            <Link href={footer.href} className={`${textLinkClass} self-start`}>
              {footer.text}
            </Link>
          )}
          <div className="fixed inset-x-0 bottom-0 border-t border-border bg-background">
            <div className="mx-auto max-w-lg px-6 pt-3 pb-6">
              <Button type="submit" size="lg" disabled={!ready || pending}>
                {pending ? "Please wait…" : submitLabel}
              </Button>
            </div>
          </div>
        </form>
      )}
    </AuthShell>
  );
}
