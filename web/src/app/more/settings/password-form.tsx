"use client";

import { useState, type FormEvent } from "react";

import { NewPasswordFields } from "@/components/new-password-fields";
import { PasswordField } from "@/components/password-field";
import { Button, SavedStatus } from "@/components/ui";
import { WEAK_PASSWORD, passwordIsStrong } from "@/lib/password";

export function PasswordForm() {
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);
  const [saved, setSaved] = useState(false);
  const [fieldsKey, setFieldsKey] = useState(0);

  async function onSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const form = e.currentTarget;
    const { current_password, new_password, confirm_password } = Object.fromEntries(new FormData(form));
    setError(null);
    setSaved(false);
    if (!passwordIsStrong(String(new_password))) {
      setError(WEAK_PASSWORD);
      return;
    }
    if (new_password !== confirm_password) {
      setError("The new passwords do not match");
      return;
    }
    setPending(true);
    try {
      const res = await fetch("/api/auth/change-password", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ current_password, new_password }),
      });
      if (!res.ok) {
        const data = (await res.json().catch(() => null)) as { error?: string } | null;
        setError(data?.error ?? "Something went wrong");
        return;
      }
      form.reset();
      setFieldsKey((k) => k + 1);
      setSaved(true);
    } catch {
      setError("Network error. Please try again.");
    } finally {
      setPending(false);
    }
  }

  return (
    <form method="post" onSubmit={onSubmit} onChange={() => setError(null)} className="flex flex-col gap-[22px]">
      <PasswordField
        id="current_password"
        name="current_password"
        label="Current password"
        autoComplete="current-password"
        required
      />
      <NewPasswordFields key={fieldsKey} name="new_password" label="New password" onSuggest={() => setError(null)} />
      {error && (
        <p role="alert" className="text-sm text-red">
          {error}
        </p>
      )}
      <SavedStatus show={saved}>Password changed. Your other devices were signed out.</SavedStatus>
      <Button type="submit" disabled={pending}>
        {pending ? "Please wait…" : "Save Password"}
      </Button>
    </form>
  );
}
