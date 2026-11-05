"use client";

import Link from "next/link";
import { useEffect, useState, type ReactNode } from "react";

import { api } from "@/lib/api-client";
import { canEditProducts, type Me } from "@/lib/types";

import { Card } from "./ui";

/**
 * Show children only to managers and secretaries. Members get a short message instead.
 * This is for a clear screen only: the API itself rejects member writes with 403.
 */
export function RequireWriter({ children }: { children: ReactNode }) {
  const [me, setMe] = useState<Me | null | "error">(null);
  useEffect(() => {
    api<Me>("auth/me").then(setMe, () => setMe("error"));
  }, []);

  if (me === null) return <p className="text-muted">Loading…</p>;
  if (me === "error") return <p className="text-red">Could not load your account.</p>;
  if (!canEditProducts(me.role)) {
    return (
      <Card>
        <p className="text-text">Only managers and secretaries can change products.</p>
        <Link href="/stock" className="mt-3 inline-block text-sm font-medium text-accent hover:underline">
          Back to stock
        </Link>
      </Card>
    );
  }
  return <>{children}</>;
}
