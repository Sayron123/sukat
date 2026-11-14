"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { MascotMessage } from "@/components/mascot";
import { PageHeader } from "@/components/page-header";
import { Card, Loading, StockBadge, isOutOfStock } from "@/components/ui";
import { api } from "@/lib/api-client";
import { formatQty } from "@/lib/format";
import type { LowStockItem } from "@/lib/types";

/** Products at or below their low-stock level, lowest stock first. */
export function LowStockList() {
  const [items, setItems] = useState<LowStockItem[] | null | "error">(null);
  useEffect(() => {
    api<LowStockItem[]>("reports/low-stock").then(setItems, () => setItems("error"));
  }, []);

  return (
    <>
      <PageHeader
        eyebrow={Array.isArray(items) ? `${items.length} product${items.length === 1 ? "" : "s"}` : " "}
        title="Low stock"
        back="/"
      />
      {items === null ? (
        <Loading />
      ) : items === "error" ? (
        <p className="text-red">Could not load low stock.</p>
      ) : items.length === 0 ? (
        <Card>
          <MascotMessage emote="happy" title="Nothing is low">
            Products get a low-stock alert from their edit screen.
          </MascotMessage>
        </Card>
      ) : (
        <ul className="flex flex-col gap-3">
          {items.map((p) => (
            <li key={p.product_id}>
              <Link href={`/stock/${p.product_id}`} className="block rounded-card">
                <Card className="flex min-h-[88px] items-center gap-2 hover:bg-surface">
                  <div className="min-w-0 flex-1">
                    <p className="flex items-center gap-[7px]">
                      <b className="min-w-0 text-base text-text">{p.name}</b>
                      <StockBadge qty={p.stock_qty} low />
                    </p>
                    <small className="mt-[5px] block text-sm text-muted">
                      Alert at {formatQty(p.low_stock_level)} {p.base_unit}
                    </small>
                  </div>
                  <div className="min-w-[62px] shrink-0 text-right">
                    <strong
                      className={`block text-2xl leading-none ${isOutOfStock(p.stock_qty) ? "text-red" : "text-text"}`}
                    >
                      {formatQty(p.stock_qty)}
                    </strong>
                    <span className="text-[13px] text-muted">{p.base_unit} left</span>
                  </div>
                </Card>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </>
  );
}
