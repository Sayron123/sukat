import Link from "next/link";
import type { ReactNode } from "react";

import { LAST_UPDATED } from "@/lib/legal";

/** Layout for the public Privacy and Terms pages: readable text, no sign-in needed. */
export function LegalPage({ title, children }: { title: string; children: ReactNode }) {
  return (
    <main className="mx-auto w-full max-w-2xl flex-1 px-6 pt-10 pb-16 text-text">
      <Link href="/" className="text-sm text-muted underline">
        Sukat
      </Link>
      <h1 className="mt-4 text-[28px] leading-tight font-bold">{title}</h1>
      <p className="mt-2 text-sm text-muted">Last updated {LAST_UPDATED}</p>
      <div className="legal mt-8 flex flex-col gap-4 text-[15px] leading-relaxed">{children}</div>
      <p className="mt-10 flex gap-4 text-sm text-muted">
        <Link href="/privacy" className="underline">
          Privacy
        </Link>
        <Link href="/terms" className="underline">
          Terms
        </Link>
      </p>
    </main>
  );
}

export function H2({ children }: { children: ReactNode }) {
  return <h2 className="mt-6 text-lg font-bold">{children}</h2>;
}

export function List({ children }: { children: ReactNode }) {
  return <ul className="flex list-disc flex-col gap-2 pl-5">{children}</ul>;
}
