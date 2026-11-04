import Link from "next/link";

import { Card } from "@/components/ui";

import { ApiStatus } from "./api-status";

export default function Home() {
  return (
    <main className="flex flex-1 items-center justify-center p-4">
      <Card className="w-full max-w-sm">
        <h1 className="text-2xl font-semibold text-accent">Sukat</h1>
        <p className="mt-1 text-sm text-muted">Inventory and sales for hardware stores</p>
        <div className="mt-4">
          <ApiStatus />
        </div>
        <div className="mt-6 flex gap-3">
          <Link
            href="/login"
            className="flex h-11 flex-1 items-center justify-center rounded-button bg-accent font-medium text-white hover:bg-accent-pressed"
          >
            Log in
          </Link>
          <Link
            href="/signup"
            className="flex h-11 flex-1 items-center justify-center rounded-button border border-border bg-background font-medium text-text hover:bg-surface"
          >
            Create store
          </Link>
        </div>
      </Card>
    </main>
  );
}
