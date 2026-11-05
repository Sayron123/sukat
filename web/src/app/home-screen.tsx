"use client";

import Link from "next/link";
import { useEffect, useState, useSyncExternalStore } from "react";

import { Icon } from "@/components/icons";
import { PageHeader } from "@/components/page-header";
import { Avatar, Badge, Card } from "@/components/ui";
import { TXN_TITLE } from "@/lib/labels";
import { api } from "@/lib/api-client";
import { STORE_TZ } from "@/lib/dates";
import { formatPeso, formatShortWhen } from "@/lib/format";
import type { LowStockItem, Me, SalesSummary, ScanToReview, TransactionPage } from "@/lib/types";

const RECENT = 5;
const noopSubscribe = () => () => {};
// Today's date in store time ("" during server render, so no mismatch).
const todayText = () =>
  new Date().toLocaleDateString("en-PH", { timeZone: STORE_TZ, weekday: "long", day: "numeric", month: "long" });

/**
 * Home tab: today's sales (vs yesterday), low stock and photos to review, and recent
 * activity. Each card opens its full list.
 */
export function HomeScreen() {
  const [me, setMe] = useState<Me | null>(null);
  const today = useSyncExternalStore(noopSubscribe, todayText, () => "");
  const [recent, setRecent] = useState<TransactionPage | null | "error">(null);
  const [sales, setSales] = useState<SalesSummary | null | "error">(null);
  const [low, setLow] = useState<number | null>(null);
  const [toReview, setToReview] = useState<number | null>(null);

  useEffect(() => {
    api<Me>("auth/me").then(setMe, () => {});
    api<TransactionPage>("transactions?page=1").then(setRecent, () => setRecent("error"));
    // No dates = today in Manila (the server decides, so the phone's clock doesn't matter).
    api<SalesSummary>("reports/sales-summary").then(setSales, () => setSales("error"));
    api<LowStockItem[]>("reports/low-stock").then((r) => setLow(r.length), () => {});
    api<ScanToReview[]>("reports/scans-to-review").then((r) => setToReview(r.length), () => {});
  }, []);

  return (
    <>
      <PageHeader
        eyebrow={today || " "}
        title={me?.store_name ?? "Sukat"}
        action={
          me && (
            <Link href="/more" aria-label="Account and settings" className="rounded-full">
              <Avatar name={me.full_name} />
            </Link>
          )
        }
      />

      <Link
        href="/transactions?range=today&type=sale"
        aria-label="Today's sales, open the list"
        className="mb-3 block rounded-card bg-surface p-4 text-text hover:bg-border/60"
      >
        <span className="flex items-center justify-between text-sm text-muted">
          <span>Today’s sales</span>
          {sales && sales !== "error" && <ChangeBadge summary={sales} />}
        </span>
        <strong className="mt-3.5 block text-[32px] leading-tight">
          {sales === null ? "…" : sales === "error" ? "—" : formatPeso(sales.total_centavos)}
        </strong>
        <span className="mt-2 block text-sm text-muted">
          {sales === "error"
            ? "Could not load sales."
            : sales
              ? `${sales.sales_count} sale${sales.sales_count === 1 ? "" : "s"} today · yesterday ${formatPeso(sales.previous.total_centavos)}`
              : " "}
        </span>
      </Link>

      <div className="mb-8 grid grid-cols-2 gap-3">
        <StatusLink href="/stock/low" count={low} tone="red" label="Low stock" />
        <StatusLink href="/scans/review" count={toReview} tone="amber" label="Needs review" />
      </div>

      <div className="mb-3 flex items-center justify-between">
        <h2 className="text-lg font-bold text-text">Recent activity</h2>
        <Link href="/transactions" className="flex min-h-10 items-center text-[13px] font-semibold text-muted">
          View all
        </Link>
      </div>

      {recent === null ? (
        <p className="text-muted">Loading…</p>
      ) : recent === "error" ? (
        <p className="text-red">Could not load recent activity.</p>
      ) : recent.items.length === 0 ? (
        <Card className="text-muted">No sales or deliveries yet. Scan a receipt to get started.</Card>
      ) : (
        <Card className="py-1">
          <ul>
            {recent.items.slice(0, RECENT).map((t) => (
              <li key={t.id}>
                <Link href={`/transactions/${t.id}`} className="flex min-h-[82px] items-center gap-3.5">
                  <span className="grid h-10 w-8 place-items-center text-text">
                    <Icon name={t.type === "sale" ? "receipt" : "box"} size={20} />
                  </span>
                  <span className="min-w-0 flex-1">
                    <span className="flex items-center gap-1.5">
                      <b className="text-base text-text">{TXN_TITLE[t.type]}</b>
                      {t.status === "voided" && <Badge tone="red">Voided</Badge>}
                    </span>
                    <small className="mt-1 block truncate text-sm text-muted">
                      {t.item_count} item{t.item_count === 1 ? "" : "s"} · {formatShortWhen(t.created_at)}
                    </small>
                  </span>
                  <strong
                    className={`shrink-0 text-base ${t.status === "voided" ? "text-subtle line-through" : "text-text"}`}
                  >
                    {formatPeso(t.total_centavos)}
                  </strong>
                </Link>
              </li>
            ))}
          </ul>
        </Card>
      )}
    </>
  );
}

/** "+12%" (green), "−8%" (red) or "0%" against the day before; nothing to compare = no badge. */
function ChangeBadge({ summary }: { summary: SalesSummary }) {
  const pct = summary.change_pct;
  if (pct === null) return null;
  const tone = pct > 0 ? "green" : pct < 0 ? "red" : "neutral";
  const text = `${pct > 0 ? "+" : pct < 0 ? "−" : ""}${Math.abs(pct)}%`;
  return (
    <Badge tone={tone} aria-label={`${text} compared with yesterday`}>
      {text}
    </Badge>
  );
}

function StatusLink({
  href,
  count,
  tone,
  label,
}: {
  href: string;
  count: number | null;
  tone: "red" | "amber";
  label: string;
}) {
  return (
    <Link
      href={href}
      className="flex min-h-[76px] items-center gap-2 rounded-card border border-border bg-background px-3 py-4 text-text hover:bg-surface min-[380px]:px-4"
    >
      <Badge tone={count ? tone : "neutral"} className="min-w-7">
        {count ?? "…"}
      </Badge>
      <span className="min-w-0 flex-1 text-[13px] font-semibold whitespace-nowrap">{label}</span>
      {/* The arrow doesn't fit on the narrowest phones; the whole card is the link. */}
      <Icon name="chevron" size={18} className="hidden min-[380px]:block" />
    </Link>
  );
}
