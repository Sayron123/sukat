"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { SavedStatus } from "@/components/ui";
import { ApiError, api } from "@/lib/api-client";

const SAVED_SHOWN_MS = 4000;

export function useSavedFlag() {
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    if (!saved) return;
    const timer = setTimeout(() => setSaved(false), SAVED_SHOWN_MS);
    return () => clearTimeout(timer);
  }, [saved]);

  return [saved, setSaved] as const;
}

export function useSave(path: string, method: "PATCH" | "POST", failure: string) {
  const router = useRouter();
  const [pending, setPending] = useState(false);
  const [saved, setSaved] = useSavedFlag();
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
  return <SavedStatus show={saved} />;
}
