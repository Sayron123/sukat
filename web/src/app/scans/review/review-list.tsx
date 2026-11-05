"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { Icon } from "@/components/icons";
import { PageHeader } from "@/components/page-header";
import { Badge, Card, Loading } from "@/components/ui";
import { api } from "@/lib/api-client";
import { formatShortWhen } from "@/lib/format";
import type { ScanToReview } from "@/lib/types";

/** Photos read in the last 7 days but not saved yet. Tap one to finish its review. */
export function ReviewList() {
  const [items, setItems] = useState<ScanToReview[] | null | "error">(null);
  useEffect(() => {
    api<ScanToReview[]>("reports/scans-to-review").then(setItems, () => setItems("error"));
  }, []);

  return (
    <>
      <PageHeader
        eyebrow={Array.isArray(items) ? `${items.length} photo${items.length === 1 ? "" : "s"}` : " "}
        title="Needs review"
        back="/"
      />
      {items === null ? (
        <Loading />
      ) : items === "error" ? (
        <p className="text-red">Could not load photos to review.</p>
      ) : items.length === 0 ? (
        <Card className="text-muted">Nothing waiting. Every scanned photo from the last 7 days is saved.</Card>
      ) : (
        <ul className="border-t border-border">
          {items.map((s) => (
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
                    <Badge tone="amber">Review</Badge>
                  </span>
                  <small className="mt-[5px] block truncate text-sm text-muted">
                    {s.line_count} line{s.line_count === 1 ? "" : "s"} · {formatShortWhen(s.created_at)}
                    {s.created_by_name && ` · ${s.created_by_name}`}
                  </small>
                </span>
                <Icon name="chevron" size={19} />
              </Link>
            </li>
          ))}
        </ul>
      )}
    </>
  );
}
