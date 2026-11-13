"use client";

import { useEffect, useState, type ReactNode } from "react";

import { api } from "@/lib/api-client";
import { canEditProducts, type Me } from "@/lib/types";

import { PageHeader } from "./page-header";
import { Loading, Notice } from "./ui";

/**
 * Show children only to managers and secretaries. Members get a short message instead.
 * This is for a clear screen only: the API itself rejects member writes with 403.
 */
export function RequireWriter({ children }: { children: ReactNode }) {
  const [me, setMe] = useState<Me | null | "error">(null);
  useEffect(() => {
    api<Me>("auth/me").then(setMe, () => setMe("error"));
  }, []);

  if (me === null) return <Loading />;
  if (me === "error") {
    return (
      <Notice mascot="error" title="Could not load your account" className="mt-8">
        Check your connection and open this page again.
      </Notice>
    );
  }
  if (!canEditProducts(me.role)) {
    return (
      <>
        <PageHeader title="Products" back="/stock" />
        <Notice mascot="locked" title="Managers and secretaries only">
          Only managers and secretaries can change products.
        </Notice>
      </>
    );
  }
  return <>{children}</>;
}
