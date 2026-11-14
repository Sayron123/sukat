"use client";

import Link from "next/link";
import { useEffect, useState, useSyncExternalStore } from "react";

import { Icon } from "@/components/icons";
import { MascotMessage } from "@/components/mascot";
import { PageHeader } from "@/components/page-header";
import { Avatar, Badge, Card } from "@/components/ui";
import { TXN_TITLE } from "@/lib/labels";
import { api } from "@/lib/api-client";
import { STORE_TZ } from "@/lib/dates";
import { formatCount, formatPeso, formatShortWhen } from "@/lib/format";
import {
  type LowStockItem,
  type Me,
  type SalesSummary,
  type ScansToReview,
  type TransactionPage,
} from "@/lib/types";

const RECENT = 5;
const noopSubscribe = () => () => {};
// Today's date in store time ("" during server render, so no mismatch).
const todayText = () =>
  new Date().toLocaleDateString("en-PH", { timeZone: STORE_TZ, weekday: "long", day: "numeric", month: "long" });

/**
 * Home tab: today's sales (vs yesterday up to the same time), low stock and photos to
 * review, and recent activity. Each card opens its full list.
 */
export function HomeScreen() {
  const [me, setMe] = useState<Me | null>(null);
  const today = useSyncExternalStore(noopSubscribe, todayText, () => "");
  const [recent, setRecent] = useState<TransactionPage | null | "error">(null);
  const [sales, setSales] = useState<SalesSummary | null | "error">(null);
  const [low, setLow] = useState<Count>(null);
  const [toReview, setToReview] = useState<Count>(null);

  useEffect(() => {
    api<Me>("auth/me").then(setMe, () => {});
    api<TransactionPage>("transactions?page=1").then(setRecent, () => setRecent("error"));
    // No dates = today in Manila (the server decides, so the phone's clock doesn't matter).
    api<SalesSummary>("reports/sales-summary").then(setSales, () => setSales("error"));
    api<LowStockItem[]>("reports/low-stock").then(
      (r) => setLow({ n: r.length, more: false }),
      () => setLow("error"),
    );
    api<ScansToReview>("reports/scans-to-review").then(
      (r) => setToReview({ n: r.items.length, more: r.has_more }),
      () => setToReview("error"),
    );
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
              ? `${sales.sales_count} sale${sales.sales_count === 1 ? "" : "s"} today · ${sales.compared_to} ${formatPeso(sales.previous.total_centavos)}`
              : " "}
        </span>
      </Link>

      <NeedsYouCard low={low} toReview={toReview} />

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
        <Card>
          <MascotMessage emote="empty">No sales or deliveries yet. Scan a receipt to get started.</MascotMessage>
        </Card>
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

/**
 * "+12%" (green), "−8%" (red) or "0%" against `compared_to` ("same time yesterday": the
 * server cuts yesterday at this time of day, so a quiet morning doesn't look like a drop).
 * Nothing to compare = no badge.
 */
function ChangeBadge({ summary }: { summary: SalesSummary }) {
  const pct = summary.change_pct;
  if (pct === null) return null;
  const tone = pct > 0 ? "green" : pct < 0 ? "red" : "neutral";
  const text = `${pct > 0 ? "+" : pct < 0 ? "−" : ""}${Math.abs(pct)}%`;
  return (
    <Badge tone={tone} aria-label={`${text} compared with ${summary.compared_to}`}>
      {text}
    </Badge>
  );
}

type Count = { n: number; more: boolean } | "error" | null;

function NeedsYouCard({ low, toReview }: { low: Count; toReview: Count }) {
  if (low === null || toReview === null) {
    return <Card className="mb-8 text-sm text-muted">Checking what needs you…</Card>;
  }
  if (low === "error" && toReview === "error") {
    return <Card className="mb-8 text-sm text-red">Could not load what needs you.</Card>;
  }
  const rows: { href: string; tone: "red" | "amber"; text: string }[] = [];
  if (low === "error") rows.push({ href: "/stock/low", tone: "red", text: "Could not load low stock" });
  else if (low.n > 0)
    rows.push({
      href: "/stock/low",
      tone: "red",
      text: `${low.n} ${low.n === 1 ? "product is" : "products are"} low on stock`,
    });
  if (toReview === "error") rows.push({ href: "/scans/review", tone: "amber", text: "Could not load scans to check" });
  else if (toReview.n > 0)
    rows.push({
      href: "/scans/review",
      tone: "amber",
      text: `${formatCount(toReview.n, toReview.more)} scanned ${toReview.n === 1 && !toReview.more ? "receipt" : "receipts"} to check`,
    });

  if (rows.length === 0) {
    return (
      <Card className="mb-8 flex items-center gap-3">
        <span className="grid h-8 w-8 shrink-0 place-items-center rounded-full bg-green-soft text-green-text">
          <Icon name="check" size={16} />
        </span>
        <span className="text-sm font-semibold text-text">Nothing needs you right now</span>
      </Card>
    );
  }

  const total = (low === "error" ? 0 : low.n) + (toReview === "error" ? 0 : toReview.n);
  const more = toReview !== "error" && toReview.more;
  return (
    <Card padded={false} className="mb-8 overflow-hidden">
      {total > 0 && (
        <h2 className="px-4 pt-4 pb-2 text-base font-bold text-text">
          {formatCount(total, more)} {total === 1 && !more ? "thing needs" : "things need"} you
        </h2>
      )}
      <ul>
        {rows.map((r, i) => (
          <li key={r.href} className={i > 0 ? "border-t border-border" : ""}>
            <Link href={r.href} className="flex min-h-14 items-center gap-3 px-4 text-text hover:bg-border/40">
              <span aria-hidden className={`h-2.5 w-2.5 shrink-0 rounded-full ${r.tone === "red" ? "bg-red" : "bg-amber"}`} />
              <span className="min-w-0 flex-1 text-sm font-semibold">{r.text}</span>
              <Icon name="chevron" size={18} className="shrink-0 text-muted" />
            </Link>
          </li>
        ))}
      </ul>
    </Card>
  );
}
