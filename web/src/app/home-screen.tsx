"use client";

import Link from "next/link";
import { useEffect, useState, useSyncExternalStore } from "react";

import { Icon } from "@/components/icons";
import { Mascot, MascotMessage } from "@/components/mascot";
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
  type TransactionType,
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
        className="mb-4 block rounded-card border border-border bg-surface p-4 text-text hover:bg-border/40"
      >
        <span className="flex items-center justify-between text-sm font-semibold text-muted">
          <span>Today’s sales</span>
          {sales && sales !== "error" && <ChangeBadge summary={sales} />}
        </span>
        <strong className="mt-1 block text-[40px] leading-tight font-extrabold">
          {sales === null ? "…" : sales === "error" ? "—" : formatPeso(sales.total_centavos)}
        </strong>
        <span className="mt-1 block text-sm text-muted">
          {sales === "error" ? "Could not load sales." : sales ? salesLine(sales) : " "}
        </span>
      </Link>

      <NeedsYouCard low={low} toReview={toReview} />

      <div className="mb-2 flex items-center justify-between">
        <h2 className="text-[17px] font-bold text-text">Recent activity</h2>
        <Link
          href="/transactions"
          className="flex min-h-10 items-center text-sm font-semibold text-accent-text underline"
        >
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
        <ul className="overflow-hidden rounded-card border border-border bg-surface">
          {recent.items.slice(0, RECENT).map((t, i) => {
            const voided = t.status === "voided";
            const sale = t.type === "sale";
            return (
              <li key={t.id} className={i > 0 ? "mx-4 border-t border-border" : "mx-4"}>
                <Link href={`/transactions/${t.id}`} className="-mx-4 flex min-h-16 items-center gap-3 px-4 py-3 hover:bg-border/40">
                  <span
                    className={`grid h-10 w-10 shrink-0 place-items-center rounded-full bg-background ${
                      sale && !voided ? "text-green-text" : "text-muted"
                    }`}
                  >
                    <Icon name={sale ? "receipt" : "box"} size={20} />
                  </span>
                  <span className="min-w-0 flex-1">
                    <span className="flex items-center gap-1.5">
                      <b className="text-[15px] text-text">{TXN_TITLE[t.type]}</b>
                      {voided && <Badge tone="red">Voided</Badge>}
                    </span>
                    <small className="mt-0.5 block truncate text-[13px] text-muted">
                      {t.item_count} item{t.item_count === 1 ? "" : "s"} · {formatShortWhen(t.created_at)}
                    </small>
                  </span>
                  <span className="shrink-0 text-right">
                    <strong
                      className={`block text-base font-bold ${
                        voided ? "text-subtle line-through" : sale ? "text-green-text" : "text-text"
                      }`}
                    >
                      {sale && !voided ? "+" : ""}
                      {formatPeso(t.total_centavos)}
                    </strong>
                    {AMOUNT_NOTE[t.type] && <small className="text-xs text-muted">{AMOUNT_NOTE[t.type]}</small>}
                  </span>
                </Link>
              </li>
            );
          })}
        </ul>
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

const AMOUNT_NOTE: Partial<Record<TransactionType, string>> = { sale: "money in", stock_in: "stock value" };

function salesLine(sales: SalesSummary): string {
  const count =
    sales.sales_count === 0
      ? "No sales yet today"
      : `${sales.sales_count} sale${sales.sales_count === 1 ? "" : "s"} today`;
  const before = sales.compared_to.charAt(0).toUpperCase() + sales.compared_to.slice(1);
  return `${count} · ${before}: ${formatPeso(sales.previous.total_centavos)}`;
}

type Count = { n: number; more: boolean } | "error" | null;

const needsCardClass = "mb-6 rounded-card border border-border bg-surface";

const TONES = {
  red: { icon: "alert", tile: "bg-red-soft text-red" },
  amber: { icon: "checklist", tile: "bg-amber-soft text-amber-text" },
} as const;

function NeedsYouCard({ low, toReview }: { low: Count; toReview: Count }) {
  if (low === null || toReview === null) {
    return <div className={`${needsCardClass} p-4 text-sm text-muted`}>Checking what needs you…</div>;
  }
  if (low === "error" && toReview === "error") {
    return <div className={`${needsCardClass} p-4 text-sm text-red`}>Could not load what needs you.</div>;
  }
  const rows: { href: string; tone: keyof typeof TONES; text: string; detail: string }[] = [];
  if (low === "error")
    rows.push({ href: "/stock/low", tone: "red", text: "Could not load low stock", detail: "Tap to open the list" });
  else if (low.n > 0)
    rows.push({
      href: "/stock/low",
      tone: "red",
      text: `${low.n} ${low.n === 1 ? "product is" : "products are"} low on stock`,
      detail: "See what to reorder",
    });
  if (toReview === "error")
    rows.push({ href: "/scans/review", tone: "amber", text: "Could not load scans to check", detail: "Tap to open the list" });
  else if (toReview.n > 0)
    rows.push({
      href: "/scans/review",
      tone: "amber",
      text: `${formatCount(toReview.n, toReview.more)} scanned ${toReview.n === 1 && !toReview.more ? "receipt" : "receipts"} to check`,
      detail: "Read but not saved yet",
    });

  if (rows.length === 0) {
    return (
      <div className={`${needsCardClass} flex items-center gap-3 p-3`}>
        <Mascot emote="happy" size={56} alt="" />
        <span className="text-[15px] font-bold text-text">Nothing needs you right now</span>
      </div>
    );
  }

  const total = (low === "error" ? 0 : low.n) + (toReview === "error" ? 0 : toReview.n);
  const more = toReview !== "error" && toReview.more;
  return (
    <div className={`${needsCardClass} flex flex-col gap-2 p-3`}>
      <div className="px-1 pt-1">
        <h2 className="text-[17px] font-bold text-text">
          {total > 0
            ? `${formatCount(total, more)} ${total === 1 && !more ? "thing needs" : "things need"} you`
            : "Something needs you"}
        </h2>
        <p className="text-[13px] text-muted">Tap one to fix it.</p>
      </div>
      <ul className="flex flex-col gap-2">
        {rows.map((r) => (
          <li key={r.href}>
            <Link
              href={r.href}
              className="flex min-h-15 items-center gap-3 rounded-button bg-background px-3 py-2 text-text hover:bg-border/40"
            >
              <span className={`grid h-9 w-9 shrink-0 place-items-center rounded-[10px] ${TONES[r.tone].tile}`}>
                <Icon name={TONES[r.tone].icon} size={20} />
              </span>
              <span className="min-w-0 flex-1">
                <b className="block text-[15px]">{r.text}</b>
                <small className="mt-0.5 block text-[13px] text-muted">{r.detail}</small>
              </span>
              <Icon name="chevron" size={20} className="shrink-0 text-muted" />
            </Link>
          </li>
        ))}
      </ul>
    </div>
  );
}
