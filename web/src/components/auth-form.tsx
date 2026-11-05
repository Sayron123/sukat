"use client";

import Link from "next/link";
import { useState, useSyncExternalStore, type FormEvent } from "react";

import { hardNavigate } from "@/lib/hard-navigate";

import { Button, Card, Field } from "./ui";

const noopSubscribe = () => () => {};

type FieldDef = {
  name: string;
  label: string;
  type?: string;
  autoComplete?: string;
  minLength?: number;
};

export function AuthForm({
  title,
  endpoint,
  fields,
  submitLabel,
  footer,
}: {
  title: string;
  endpoint: string;
  fields: FieldDef[];
  submitLabel: string;
  footer: { text: string; href: string; link: string };
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
      hardNavigate("/stock");
    } catch {
      setError("Network error. Please try again.");
    } finally {
      setPending(false);
    }
  }

  return (
    <main className="flex flex-1 items-center justify-center p-4">
      <Card className="w-full max-w-sm">
        <h1 className="text-2xl font-semibold text-text">{title}</h1>
        <form method="post" onSubmit={onSubmit} className="mt-6 flex flex-col gap-4">
          {fields.map((f) => (
            <Field
              key={f.name}
              id={f.name}
              name={f.name}
              label={f.label}
              type={f.type ?? "text"}
              autoComplete={f.autoComplete}
              minLength={f.minLength}
              required
            />
          ))}
          {error && (
            <p role="alert" className="text-sm text-red">
              {error}
            </p>
          )}
          <Button type="submit" disabled={!ready || pending}>
            {pending ? "Please wait…" : submitLabel}
          </Button>
        </form>
        <p className="mt-4 text-sm text-muted">
          {footer.text}{" "}
          <Link href={footer.href} className="font-medium text-accent hover:underline">
            {footer.link}
          </Link>
        </p>
      </Card>
    </main>
  );
}
