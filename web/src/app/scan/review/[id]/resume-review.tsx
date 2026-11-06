"use client";

import { useEffect, useState } from "react";

import { PageHeader } from "@/components/page-header";
import { Loading } from "@/components/ui";
import { ApiError, api } from "@/lib/api-client";
import type { Scan } from "@/lib/types";

import { ScanFlow } from "../../scan-flow";

/** Load a scan that was read earlier and continue its review. */
export function ResumeReview({ id }: { id: string }) {
  const [scan, setScan] = useState<Scan | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api<Scan>(`scans/${encodeURIComponent(id)}`).then(setScan, (e: unknown) =>
      setError(e instanceof ApiError && (e.status === 404 || e.status === 422) ? "Photo not found." : "Could not load it."),
    );
  }, [id]);

  if (error)
    return (
      <>
        <PageHeader title="Review" back="/scans/review" />
        <p className="text-red">{error}</p>
      </>
    );
  if (!scan) return <Loading />;
  return <ScanFlow key={scan.id} mode={scan.type} initialScan={scan} exitHref="/scans/review" />;
}
