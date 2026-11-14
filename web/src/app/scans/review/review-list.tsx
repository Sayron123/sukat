"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { Icon } from "@/components/icons";
import { MascotMessage } from "@/components/mascot";
import { PageHeader } from "@/components/page-header";
import { Badge, Card, Loading } from "@/components/ui";
import { api } from "@/lib/api-client";
import { formatCount, formatShortWhen } from "@/lib/format";
import type { ScanMode, ScansToReview } from "@/lib/types";

const TYPES: { value: ScanMode; label: string; icon: "box" | "receipt"; empty: string }[] = [
  { value: "stock_in", label: "Delivery", icon: "box", empty: "No delivery lists waiting." },
  { value: "sale", label: "Sale", icon: "receipt", empty: "No sale receipts waiting." },
];

/**
 * Photos from the last 7 days that were read but not saved, or couldn't be read.
 * Tap one to finish its review (or try reading it again).
 */
export function ReviewList() {
  const [list, setList] = useState<ScansToReview | null | "error">(null);
  const [picked, setPicked] = useState<ScanMode | null>(null);
  useEffect(() => {
    api<ScansToReview>("reports/scans-to-review").then(setList, () => setList("error"));
  }, []);
  const items = list === null || list === "error" ? list : list.items;
  const hasMore = list !== null && list !== "error" && list.has_more;
  const counts = {
    stock_in: Array.isArray(items) ? items.filter((s) => s.type === "stock_in").length : 0,
    sale: Array.isArray(items) ? items.filter((s) => s.type === "sale").length : 0,
  };
  const type = picked ?? (counts.stock_in === 0 && counts.sale > 0 ? "sale" : "stock_in");
  const shown = Array.isArray(items) ? items.filter((s) => s.type === type) : items;

  return (
    <>
      <PageHeader
        eyebrow={Array.isArray(items) ? photoCount(items.length, hasMore) : " "}
        title="Needs review"
        back="/"
      />
      {Array.isArray(items) && items.length > 0 && (
        <div role="group" aria-label="Show" className="mb-5 grid grid-cols-2 gap-1 rounded-button bg-surface p-1">
          {TYPES.map((t) => (
            <button
              key={t.value}
              type="button"
              aria-pressed={type === t.value}
              onClick={() => setPicked(t.value)}
              className={`flex h-10 items-center justify-center gap-2 rounded-[9px] text-sm font-bold ${
                type === t.value ? "bg-background text-text shadow-sm" : "text-muted"
              }`}
            >
              <Icon name={t.icon} size={18} />
              {t.label} ({counts[t.value]})
            </button>
          ))}
        </div>
      )}
      {items === null ? (
        <Loading />
      ) : items === "error" ? (
        <p className="text-red">Could not load photos to review.</p>
      ) : items.length === 0 ? (
        <Card>
          <MascotMessage emote="happy" title="Nothing waiting">
            Every scanned photo from the last 7 days is saved.
          </MascotMessage>
        </Card>
      ) : shown !== null && shown !== "error" && shown.length === 0 ? (
        <Card className="text-muted">{TYPES.find((t) => t.value === type)?.empty}</Card>
      ) : (
        <ul className="border-t border-border">
          {(shown as ScansToReview["items"]).map((s) => (
            <li key={s.scan_id}>
              <Link
                href={`/scan/review/${s.scan_id}`}
                className="flex min-h-[82px] items-center gap-3 border-b border-border py-[11px]"
              >
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
