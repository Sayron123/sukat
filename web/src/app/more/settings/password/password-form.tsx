"use client";

import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";

import { NewPasswordFields } from "@/components/new-password-fields";
import { PasswordField } from "@/components/password-field";
import { showToast } from "@/components/toast";
import { WEAK_PASSWORD, passwordIsStrong } from "@/lib/password";

import { EditActions, SETTINGS } from "../edit-actions";

const FORM = "password-form";

export function PasswordForm() {
  const router = useRouter();
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  async function onSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const { current_password, new_password, confirm_password } = Object.fromEntries(new FormData(e.currentTarget));
    setError(null);
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
        setPending(false);
        return;
      }
      showToast("Password changed. Your other devices were signed out.");
      router.push(SETTINGS);
    } catch {
      setError("Network error. Please try again.");
      setPending(false);
    }
  }

  return (
    <>
      <form id={FORM} method="post" onSubmit={onSubmit} onChange={() => setError(null)} className="flex flex-col gap-5.5">
        <PasswordField
          id="current_password"
          name="current_password"
          label="Current password"
          autoComplete="current-password"
          required
        />
        <NewPasswordFields
          name="new_password"
          label="New password"
          confirmLabel="Confirm new password"
          onSuggest={() => setError(null)}
        />
      </form>
      <EditActions form={FORM} label="Save password" pending={pending} error={error} />
    </>
  );
}
