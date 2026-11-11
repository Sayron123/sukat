"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { Icon } from "@/components/icons";
import { PageHeader } from "@/components/page-header";
import { ScanTypeSwitch } from "@/components/scan-type-switch";
import { Badge, Card, Loading } from "@/components/ui";
import { ApiError, api } from "@/lib/api-client";
import { formatCount, formatShortWhen } from "@/lib/format";
import { type Me, type Scan, type ScanMode, type ScansToReview, canEditProducts } from "@/lib/types";

/**
 * Photos from the last 7 days that were read but not saved, or couldn't be read.
 * Tap one to finish its review (or try reading it again).
 */
export function ReviewList() {
  const [list, setList] = useState<ScansToReview | null | "error">(null);
  const [me, setMe] = useState<Me | null>(null);
  const [switching, setSwitching] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    api<ScansToReview>("reports/scans-to-review").then(setList, () => setList("error"));
    api<Me>("auth/me").then(setMe, () => {});
  }, []);
  const canSwitch = canEditProducts(me?.role);

  async function switchType(scanId: string, type: ScanMode) {
    setSwitching(scanId);
    setError(null);
    try {
      const scan = await api<Scan>(`scans/${scanId}`, { method: "PATCH", body: JSON.stringify({ type }) });
      setList((current) =>
        current && current !== "error"
          ? { ...current, items: current.items.map((s) => (s.scan_id === scanId ? { ...s, type: scan.type } : s)) }
          : current,
      );
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not change it. Please try again.");
    } finally {
      setSwitching(null);
    }
  }
  const items = list === null || list === "error" ? list : list.items;
  const hasMore = list !== null && list !== "error" && list.has_more;

  return (
    <>
      <PageHeader
        eyebrow={Array.isArray(items) ? photoCount(items.length, hasMore) : " "}
        title="Needs review"
        back="/"
      />
      {error && (
        <p role="alert" className="mb-3 text-sm text-red">
          {error}
        </p>
      )}
      {items === null ? (
        <Loading />
      ) : items === "error" ? (
        <p className="text-red">Could not load photos to review.</p>
      ) : items.length === 0 ? (
        <Card className="text-muted">Nothing waiting. Every scanned photo from the last 7 days is saved.</Card>
      ) : (
        <ul className="border-t border-border">
          {items.map((s) => (
            <li key={s.scan_id} className="border-b border-border">
              <Link href={`/scan/review/${s.scan_id}`} className="flex min-h-[82px] items-center gap-3 py-[11px]">
                <span className="grid h-10 w-8 place-items-center text-text">
                  <Icon name={s.type === "sale" ? "receipt" : "box"} size={20} />
                </span>
                <span className="min-w-0 flex-1">
                  <span className="flex items-center gap-1.5">
                    <b className="text-base text-text">{s.type === "sale" ? "Sale receipt" : "Delivery list"}</b>
                    {s.status === "failed" ? <Badge tone="red">Failed</Badge> : <Badge tone="amber">Review</Badge>}
                  </span>
                  <small className="mt-[5px] block truncate text-sm text-muted">
                    {s.status === "failed"
                      ? "Couldn’t read"
                      : `${s.line_count} line${s.line_count === 1 ? "" : "s"}`}{" "}
                    · {formatShortWhen(s.created_at)}
                    {s.created_by_name && ` · ${s.created_by_name}`}
                  </small>
                </span>
                <Icon name="chevron" size={19} />
              </Link>
              {canSwitch && s.status === "read" && (
                <div className="-mt-1 pb-3 pl-11">
                  <ScanTypeSwitch
                    value={s.type}
                    disabled={switching !== null}
                    onChange={(type) => switchType(s.scan_id, type)}
                  />
                </div>
              )}
            </li>
          ))}
        </ul>
      )}
      {Array.isArray(items) && hasMore && (
        <p className="mt-4 text-sm text-muted">
          Showing the newest {items.length}. Older ones appear here as these are saved or tried again.
        </p>
      )}
    </>
  );
}

/** "3 photos", or "50+ photos" when the API left older ones out. */
function photoCount(n: number, more: boolean): string {
  return `${formatCount(n, more)} photo${n === 1 && !more ? "" : "s"}`;
}
