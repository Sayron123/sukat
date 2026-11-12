"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";

import { PageHeader } from "@/components/page-header";
import { Badge, Card, Chip, Field, Pager, Select } from "@/components/ui";
import { ApiError, api } from "@/lib/api-client";
import { type RangeKey, dayLabel, rangeFor, storeDate } from "@/lib/dates";
import { formatPeso, formatTime } from "@/lib/format";
import { TXN_BADGE, TXN_TITLE } from "@/lib/labels";
import type { TransactionPage, TransactionSummary, TransactionType } from "@/lib/types";

const RANGES: { key: RangeKey; label: string }[] = [
  { key: "today", label: "Today" },
  { key: "week", label: "This week" },
  { key: "month", label: "This month" },
  { key: "custom", label: "Custom dates" },
];
const TYPES: { type: TransactionType | null; label: string }[] = [
  { type: null, label: "All" },
  { type: "sale", label: "Sale" },
  { type: "stock_in", label: "Stock in" },
  { type: "adjustment", label: "Adjustment" },
];
const SIGN: Record<TransactionType, string> = { sale: "−", stock_in: "+", adjustment: "±" };

function parseRange(v: string | null): RangeKey {
  return RANGES.some((r) => r.key === v) ? (v as RangeKey) : "week";
}
function parseType(v: string | null): TransactionType | null {
  return TYPES.find((t) => t.type === v)?.type ?? null;
}

/**
 * Sales, stock-ins and adjustments, newest first, grouped by day (Manila time).
 * Filters live in the URL (?range=today&type=sale), so Home can link straight to them.
 */
export function TransactionList() {
  const router = useRouter();
  const search = useSearchParams();
  const [rangeKey, setRangeKey] = useState<RangeKey>(() => parseRange(search.get("range")));
  const [type, setType] = useState<TransactionType | null>(() => parseType(search.get("type")));
  const [custom, setCustom] = useState({ start: search.get("start") ?? "", end: search.get("end") ?? "" });
  const [page, setPage] = useState(1);
  // The last answer and the query it belongs to. Only an answer for the current query is
  // shown, so after a filter or page change the old rows and old errors disappear at
  // once ("Loading…" until the new answer), instead of looking like the new result.
  const [result, setResult] = useState<{ query: string; data?: TransactionPage; error?: string } | null>(null);

  const range = rangeFor(rangeKey, custom);
  let query: string | null = null; // null: custom dates not complete yet
  if (range) {
    const params = new URLSearchParams({ page: String(page), start: range.start, end: range.end });
    if (type) params.set("type", type);
    query = params.toString();
  }
  const current = result && result.query === query ? result : null;
  const data = current?.data ?? null;
  const error = current?.error ?? null;

  useEffect(() => {
    if (query === null) return;
    let stale = false;
    api<TransactionPage>(`transactions?${query}`).then(
      (res) => !stale && setResult({ query, data: res }),
      (e: unknown) =>
        !stale && setResult({ query, error: e instanceof ApiError ? e.message : "Could not load history" }),
    );
    return () => {
      stale = true;
    };
  }, [query]);

  /** Change a filter, start from page 1, and keep the URL in step (for Back and sharing). */
  function apply(next: { range?: RangeKey; type?: TransactionType | null; custom?: typeof custom }) {
    const r = next.range ?? rangeKey;
    const t = next.type === undefined ? type : next.type;
    const c = next.custom ?? custom;
    setRangeKey(r);
    setType(t);
    setCustom(c);
    setPage(1);
    const q = new URLSearchParams({ range: r });
    if (t) q.set("type", t);
    if (r === "custom" && c.start) q.set("start", c.start);
    if (r === "custom" && c.end) q.set("end", c.end);
    router.replace(`/transactions?${q}`, { scroll: false });
  }

  const customInvalid = rangeKey === "custom" && custom.start && custom.end && custom.end < custom.start;

  return (
    <>
      <PageHeader eyebrow="Stock movements" title="History" back="/more" />

      <Select
        id="range"
        label="Dates"
        hideLabel
        icon="calendar"
        value={rangeKey}
        onChange={(e) => apply({ range: parseRange(e.target.value) })}
        wrapperClassName="mb-3"
      >
        {RANGES.map((r) => (
          <option key={r.key} value={r.key}>
            {r.label}
          </option>
        ))}
      </Select>
      {rangeKey === "custom" && (
        <div className="mb-3 grid grid-cols-2 gap-3">
          <Field
            id="from"
            label="From"
            type="date"
            value={custom.start}
            max={custom.end || undefined}
            onChange={(e) => apply({ custom: { ...custom, start: e.target.value } })}
          />
          <Field
            id="to"
            label="To"
            type="date"
            value={custom.end}
            min={custom.start || undefined}
            onChange={(e) => apply({ custom: { ...custom, end: e.target.value } })}
          />
        </div>
      )}
      <div className="-mx-5 mb-[22px] flex gap-2 overflow-x-auto px-5 [scrollbar-width:none]" role="group" aria-label="Type">
        {TYPES.map((t) => (
          <Chip key={t.label} selected={type === t.type} onClick={() => apply({ type: t.type })}>
            {t.label}
          </Chip>
        ))}
      </div>

      {error && (
        <p role="alert" className="mb-3 text-sm text-red">
          {error}
        </p>
      )}
      {customInvalid ? (
        <p className="text-sm text-red">“To” must be on or after “From”.</p>
      ) : rangeKey === "custom" && !rangeFor("custom", custom) ? (
        <p className="text-muted">Pick both dates.</p>
      ) : !data ? (
        !error && <p className="text-muted">Loading…</p>
      ) : data.items.length === 0 ? (
        <Card className="text-center text-muted">Nothing saved in these dates.</Card>
      ) : (
        <>
          {groupByDay(data.items).map(([day, rows]) => (
            <section key={day}>
              <h2 className="mt-2 mb-2 text-[13px] font-bold text-subtle uppercase">{dayLabel(day)}</h2>
              <ul className="mb-5 border-t border-border">
                {rows.map((t) => (
                  <Row key={t.id} t={t} />
                ))}
              </ul>
            </section>
          ))}
          <Pager page={data.page} pages={data.pages} onPage={setPage} />
        </>
      )}
    </>
  );
}

/** Consecutive rows by Manila day; rows are already newest first. */
function groupByDay(items: TransactionSummary[]): [string, TransactionSummary[]][] {
  const groups: [string, TransactionSummary[]][] = [];
  for (const t of items) {
    const day = storeDate(new Date(t.created_at));
    const last = groups.at(-1);
    if (last && last[0] === day) last[1].push(t);
    else groups.push([day, [t]]);
  }
  return groups;
}

function Row({ t }: { t: TransactionSummary }) {
  const voided = t.status === "voided";
  const time = formatTime(t.created_at);
  return (
    <li>
      <Link
        href={`/transactions/${t.id}`}
        className="flex min-h-[82px] items-center gap-2 border-b border-border py-[11px]"
      >
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-1.5">
            <b className="text-base text-text">{TXN_TITLE[t.type]}</b>
            {voided ? <Badge tone="red">Voided</Badge> : <Badge>{TXN_BADGE[t.type]}</Badge>}
          </div>
          <small className="mt-[5px] block truncate text-sm text-muted">{time}</small>
        </div>
        <div className="shrink-0 text-right">
          <strong className="block text-base text-text">
            {SIGN[t.type]} {t.item_count} item{t.item_count === 1 ? "" : "s"}
          </strong>
          <small className={`mt-[5px] block text-sm ${voided ? "text-subtle line-through" : "text-muted"}`}>
            {formatPeso(t.total_centavos)}
          </small>
        </div>
      </Link>
    </li>
  );
}
