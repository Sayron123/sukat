"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { PageHeader } from "@/components/page-header";
import { Badge, Card, Chip, Pager } from "@/components/ui";
import { ApiError, api } from "@/lib/api-client";
import { formatPeso, formatShortWhen } from "@/lib/format";
import type { ScanMode, TransactionPage } from "@/lib/types";

const FILTERS: { label: string; type: ScanMode | null }[] = [
  { label: "All", type: null },
  { label: "Sales", type: "sale" },
  { label: "Stock in", type: "stock_in" },
];

/** Saved sales and stock-ins, newest first. */
export function TransactionList() {
  const [type, setType] = useState<ScanMode | null>(null);
  const [page, setPage] = useState(1);
  const [data, setData] = useState<TransactionPage | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const params = new URLSearchParams({ page: String(page) });
    if (type) params.set("type", type);
    let stale = false;
    api<TransactionPage>(`transactions?${params}`).then(
      (res) => !stale && (setData(res), setError(null)),
      (e: unknown) => !stale && setError(e instanceof ApiError ? e.message : "Could not load history"),
    );
    return () => {
      stale = true;
    };
  }, [type, page]);

  return (
    <>
      <PageHeader eyebrow="Stock movements" title="History" back="/more" />
      <div className="mb-[22px] flex gap-2" role="group" aria-label="Type">
        {FILTERS.map((f) => (
          <Chip key={f.label} selected={type === f.type} onClick={() => (setType(f.type), setPage(1))}>
            {f.label}
          </Chip>
        ))}
      </div>
      {error && (
        <p role="alert" className="mb-3 text-sm text-red">
          {error}
        </p>
      )}
      {!data ? (
        <p className="text-muted">Loading…</p>
      ) : data.items.length === 0 ? (
        <Card className="text-center text-muted">Nothing saved yet.</Card>
      ) : (
        <ul className="mb-5 border-t border-border">
          {data.items.map((t) => (
            <li key={t.id}>
              <Link
                href={`/transactions/${t.id}`}
                className="flex min-h-[82px] items-center gap-2 border-b border-border py-[11px]"
              >
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-1.5">
                    <b className="text-base text-text">{t.type === "sale" ? "Sale" : "Stock received"}</b>
                    {t.status === "voided" ? (
                      <Badge tone="red">Voided</Badge>
                    ) : (
                      <Badge>{t.type === "sale" ? "Sale" : "Stock in"}</Badge>
                    )}
                  </div>
                  <small className="mt-[5px] block truncate text-sm text-muted">{formatShortWhen(t.created_at)}</small>
                </div>
                <div className="shrink-0 text-right">
                  <strong className="block text-base text-text">
                    {t.type === "sale" ? "−" : "+"} {t.item_count} item{t.item_count === 1 ? "" : "s"}
                  </strong>
                  <small
                    className={`mt-[5px] block text-sm ${t.status === "voided" ? "text-subtle line-through" : "text-muted"}`}
                  >
                    {formatPeso(t.total_centavos)}
                  </small>
                </div>
              </Link>
            </li>
          ))}
        </ul>
      )}
      {data && <Pager page={data.page} pages={data.pages} onPage={setPage} />}
    </>
  );
}
