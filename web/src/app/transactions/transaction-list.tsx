"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { Card, Chip } from "@/components/ui";
import { ApiError, api } from "@/lib/api-client";
import { formatPeso } from "@/lib/format";
import type { ScanMode, TransactionPage } from "@/lib/types";

const FILTERS: { label: string; type: ScanMode | null }[] = [
  { label: "All", type: null },
  { label: "Sales", type: "sale" },
  { label: "Stock in", type: "stock_in" },
];

export function formatWhen(iso: string): string {
  return new Date(iso).toLocaleString("en-PH", { dateStyle: "medium", timeStyle: "short" });
}

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
    <div className="flex flex-col gap-4">
      <h1 className="text-2xl font-semibold text-text">History</h1>
      <div className="flex gap-2" role="group" aria-label="Type">
        {FILTERS.map((f) => (
          <Chip key={f.label} selected={type === f.type} onClick={() => (setType(f.type), setPage(1))}>
            {f.label}
          </Chip>
        ))}
      </div>
      {error && (
        <p role="alert" className="text-sm text-red">
          {error}
        </p>
      )}
      {!data ? (
        <p className="text-muted">Loading…</p>
      ) : data.items.length === 0 ? (
        <Card className="text-center text-muted">Nothing saved yet.</Card>
      ) : (
        <Card padded={false}>
          <ul className="divide-y divide-border">
            {data.items.map((t) => (
              <li key={t.id}>
                <Link href={`/transactions/${t.id}`} className="flex items-center justify-between gap-3 px-4 py-3">
                  <div className="min-w-0">
                    <p className="font-medium text-text">
                      {t.type === "sale" ? "Sale" : "Stock in"}
                      {t.status === "voided" && (
                        <span className="ml-2 rounded-full bg-red/10 px-2 py-0.5 text-xs font-medium text-red">
                          Voided
                        </span>
                      )}
                    </p>
                    <p className="text-sm text-muted">
                      {formatWhen(t.created_at)} · {t.item_count} item{t.item_count === 1 ? "" : "s"}
                    </p>
                  </div>
                  <span className={`shrink-0 font-medium ${t.status === "voided" ? "text-muted line-through" : "text-text"}`}>
                    {formatPeso(t.total_centavos)}
                  </span>
                </Link>
              </li>
            ))}
          </ul>
        </Card>
      )}
      {data && data.pages > 1 && (
        <div className="flex items-center justify-between">
          <button type="button" disabled={page <= 1} onClick={() => setPage(page - 1)} className="h-11 rounded-button border border-border px-4 text-sm font-medium text-text disabled:opacity-40">
            Previous
          </button>
          <span className="text-sm text-muted">
            Page {data.page} of {data.pages}
          </span>
          <button type="button" disabled={page >= data.pages} onClick={() => setPage(page + 1)} className="h-11 rounded-button border border-border px-4 text-sm font-medium text-text disabled:opacity-40">
            Next
          </button>
        </div>
      )}
    </div>
  );
}
