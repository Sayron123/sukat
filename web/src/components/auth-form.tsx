"use client";

import Link from "next/link";
import { useState, useSyncExternalStore, type FormEvent } from "react";

import { hardNavigate } from "@/lib/hard-navigate";

import { Button, Field, textLinkClass } from "./ui";

const noopSubscribe = () => () => {};

type FieldDef = {
  name: string;
  label: string;
  type?: string;
  autoComplete?: string;
  minLength?: number;
  maxLength?: number;
  optional?: boolean;
};

export function AuthForm({
  title,
  subtitle,
  endpoint,
  fields,
  submitLabel,
  footer,
}: {
  title: string;
  subtitle: string;
  endpoint: string;
  fields: FieldDef[];
  submitLabel: string;
  footer: { text: string; href: string };
}) {
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);
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
    setPending(true);
    const body = Object.fromEntries(new FormData(e.currentTarget));
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
      hardNavigate("/");
    } catch {
      setError("Network error. Please try again.");
    } finally {
      setPending(false);
    }
  }

  return (
    <main className="mx-auto w-full max-w-lg flex-1 px-6 pt-16 pb-36">
      <div
        aria-hidden
        className="mb-[30px] grid h-[52px] w-[52px] place-items-center rounded-button bg-text text-base font-bold text-white"
      >
        S
      </div>
      <p className="text-[13px] font-bold text-muted uppercase">Sukat</p>
      <h1 className="mt-1 text-[28px] leading-tight font-bold text-text">{title}</h1>
      <p className="mt-2 mb-7 text-sm text-muted">{subtitle}</p>
      <form method="post" onSubmit={onSubmit} className="flex flex-col gap-[22px]">
        {fields.map((f) => (
          <Field
            key={f.name}
            id={f.name}
            name={f.name}
            label={f.label}
            type={f.type ?? "text"}
            autoComplete={f.autoComplete}
            minLength={f.minLength}
            maxLength={f.maxLength}
            required={!f.optional}
          />
        ))}
        {error && (
          <p role="alert" className="text-sm text-red">
            {error}
          </p>
        )}
        <Link href={footer.href} className={`${textLinkClass} self-start`}>
          {footer.text}
        </Link>
        <div className="fixed inset-x-0 bottom-0 border-t border-border bg-background">
          <div className="mx-auto max-w-lg px-6 pt-3 pb-6">
            <Button type="submit" size="lg" disabled={!ready || pending}>
              {pending ? "Please wait…" : submitLabel}
            </Button>
          </div>
        </div>
      </form>
    </main>
  );
}
