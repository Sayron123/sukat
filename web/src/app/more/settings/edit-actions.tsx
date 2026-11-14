"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { ActionDock } from "@/components/action-dock";
import { showToast } from "@/components/toast";
import { Button } from "@/components/ui";
import { ApiError, api } from "@/lib/api-client";

export const SETTINGS = "/more/settings";

export function useSaveAndReturn(path: string, failure: string, done: string) {
  const router = useRouter();
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function save(body: Record<string, unknown>) {
    setError(null);
    setPending(true);
    try {
      await api(path, { method: "PATCH", body: JSON.stringify(body) });
      showToast(done);
      router.push(SETTINGS);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : failure);
      setPending(false);
    }
  }

  return { pending, error, setError, save };
}

export function EditActions({
  form,
  label,
  pending,
  error,
}: {
  form: string;
  label: string;
  pending: boolean;
  error: string | null;
}) {
  return (
    <ActionDock>
      {error && (
        <p role="alert" className="text-sm text-red">
          {error}
        </p>
      )}
      <Button type="submit" form={form} size="lg" disabled={pending}>
        {pending ? "Saving…" : label}
      </Button>
      <Link href={SETTINGS} className="grid min-h-11 place-items-center text-[15px] font-semibold text-text">
        Cancel
      </Link>
    </ActionDock>
  );
}
