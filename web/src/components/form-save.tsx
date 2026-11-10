"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { ApiError, api } from "@/lib/api-client";

export function useSave(path: string, method: "PATCH" | "POST", failure: string) {
  const router = useRouter();
  const [pending, setPending] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function save(body: Record<string, unknown>) {
    setError(null);
    setSaved(false);
    setPending(true);
    try {
      await api(path, { method, body: JSON.stringify(body) });
      setSaved(true);
      router.refresh();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : failure);
    } finally {
      setPending(false);
    }
  }

  return { pending, saved, error, save };
}

export function SaveResult({ saved, error }: { saved: boolean; error: string | null }) {
  if (error) {
    return (
      <p role="alert" className="text-sm text-red">
        {error}
      </p>
    );
  }
  return saved ? (
    <p role="status" className="text-sm text-muted">
      Saved.
    </p>
  ) : null;
}
