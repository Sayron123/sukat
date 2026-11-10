"use client";

import { useRouter } from "next/navigation";
import type { FormEvent } from "react";

import { Button, Field } from "@/components/ui";

function tokenFrom(input: string): string {
  const text = input.trim();
  return text.match(/token=([\w-]+)/)?.[1] ?? text;
}

export function JoinForm() {
  const router = useRouter();

  function onSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const link = String(new FormData(e.currentTarget).get("link") ?? "");
    router.push(`/invite?token=${encodeURIComponent(tokenFrom(link))}`);
  }

  return (
    <form onSubmit={onSubmit} className="flex flex-col gap-[22px]">
      <Field id="link" name="link" label="Paste your invite link" autoComplete="off" required />
      <div className="fixed inset-x-0 bottom-0 border-t border-border bg-background">
        <div className="mx-auto max-w-lg px-6 pt-3 pb-6">
          <Button type="submit" size="lg">
            Continue
          </Button>
        </div>
      </div>
    </form>
  );
}
