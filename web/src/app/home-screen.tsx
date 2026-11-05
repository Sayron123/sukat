"use client";

import Link from "next/link";
import { useEffect, useState, useSyncExternalStore } from "react";

import { Icon } from "@/components/icons";
import { PageHeader } from "@/components/page-header";
import { Avatar, Badge, Card } from "@/components/ui";
import { api } from "@/lib/api-client";
import { formatPeso, formatShortWhen } from "@/lib/format";
import type { Me, TransactionPage } from "@/lib/types";

const RECENT = 5;
const noopSubscribe = () => () => {};
// Today's date from the phone's clock ("" during server render, so no mismatch).
const todayText = () => new Date().toLocaleDateString("en-PH", { weekday: "long", day: "numeric", month: "long" });

/** Home tab: store name and the latest sales and stock-ins. */
export function HomeScreen() {
  const [me, setMe] = useState<Me | null>(null);
  const today = useSyncExternalStore(noopSubscribe, todayText, () => "");
  const [recent, setRecent] = useState<TransactionPage | null | "error">(null);

  useEffect(() => {
    api<Me>("auth/me").then(setMe, () => {});
    api<TransactionPage>("transactions?page=1").then(setRecent, () => setRecent("error"));
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
                      <b className="text-base text-text">{t.type === "sale" ? "Sale" : "Stock received"}</b>
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
