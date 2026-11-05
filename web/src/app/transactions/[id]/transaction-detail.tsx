"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { ConfirmDialog } from "@/components/confirm-dialog";
import { Button, Card } from "@/components/ui";
import { ApiError, api } from "@/lib/api-client";
import { formatPeso, formatQty, formatWhen } from "@/lib/format";
import { canEditProducts, type Me, type Transaction } from "@/lib/types";


/**
 * One sale or stock-in, with a Void button for managers and secretaries. Voiding asks
 * for confirmation first; the server keeps everything and adds reversing stock moves.
 */
export function TransactionDetail({ id }: { id: string }) {
  const [txn, setTxn] = useState<Transaction | null>(null);
  const [me, setMe] = useState<Me | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [confirming, setConfirming] = useState(false);
  const [voiding, setVoiding] = useState(false);

  useEffect(() => {
    api<Me>("auth/me").then(setMe, () => {});
    api<Transaction>(`transactions/${encodeURIComponent(id)}`).then(setTxn, (e: unknown) =>
      setError(e instanceof ApiError && (e.status === 404 || e.status === 422) ? "Not found." : "Could not load it."),
    );
  }, [id]);

  async function voidIt() {
    if (!txn) return;
    setVoiding(true);
    try {
      setTxn(await api<Transaction>(`transactions/${txn.id}/void`, { method: "POST" }));
      setConfirming(false);
      setError(null);
    } catch (e) {
      // Already voided (e.g. by someone else): reload so the screen shows the truth.
      if (e instanceof ApiError && e.code === "already_voided") {
        setTxn(await api<Transaction>(`transactions/${txn.id}`).catch(() => txn));
      }
      setConfirming(false);
      setError(e instanceof ApiError ? e.message : "Could not void. Try again.");
    } finally {
      setVoiding(false);
    }
  }

  if (!txn) return <p className={error ? "text-red" : "text-muted"}>{error ?? "Loading…"}</p>;

  const isSale = txn.type === "sale";
  const voided = txn.status === "voided";
  const canVoid = !voided && canEditProducts(me?.role);
  const sign = isSale ? "−" : "+";

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center justify-between gap-2">
        <h1 className="text-2xl font-semibold text-text">{isSale ? "Sale" : "Stock in"}</h1>
        <Link href="/transactions" className="text-sm font-medium text-accent hover:underline">
          History
        </Link>
      </div>

      <Card className="flex flex-col gap-1">
        <p className={`text-3xl font-semibold ${voided ? "text-muted line-through" : "text-text"}`}>
          {formatPeso(txn.total_centavos)}
        </p>
        <p className="text-sm text-muted">
          {formatWhen(txn.created_at)}
          {txn.created_by_name && ` · by ${txn.created_by_name}`}
        </p>
        {voided && (
          <p role="status" className="mt-2 rounded-button bg-red/10 px-3 py-2 text-sm text-red">
            Voided{txn.voided_at && ` ${formatWhen(txn.voided_at)}`}
            {txn.voided_by_name && ` by ${txn.voided_by_name}`}. Stock was put back.
          </p>
        )}
      </Card>

      <Card padded={false}>
        <ul className="divide-y divide-border">
          {txn.items.map((item) => (
            <li key={item.line_no} className="flex items-start justify-between gap-3 px-4 py-3">
              <div className="min-w-0">
                <p className="font-medium text-text">{item.product_name}</p>
                <p className="text-sm text-muted">
                  {sign}
                  {formatQty(item.qty)} {item.unit}
                  {item.unit_price_centavos !== null && ` × ${formatPeso(item.unit_price_centavos)}`}
                  {item.unit !== item.base_unit && ` (${formatQty(item.qty_base)} ${item.base_unit})`}
                </p>
              </div>
              <span className="shrink-0 text-sm font-medium text-text">
                {item.line_total_centavos === null ? "—" : formatPeso(item.line_total_centavos)}
              </span>
            </li>
          ))}
        </ul>
      </Card>

      {error && (
        <p role="alert" className="text-sm text-red">
          {error}
        </p>
      )}
      {canVoid && (
        <Button variant="danger" onClick={() => setConfirming(true)}>
          Void this {isSale ? "sale" : "stock in"}
        </Button>
      )}

      <ConfirmDialog
        open={confirming}
        title={`Void this ${isSale ? "sale" : "stock in"}?`}
        confirmLabel="Void"
        danger
        busy={voiding}
        onConfirm={voidIt}
        onCancel={() => setConfirming(false)}
      >
        <p>
          {isSale ? "The sold items go back into stock." : "The delivered items are taken back out of stock."} Nothing is
          deleted, and this can’t be undone.
        </p>
      </ConfirmDialog>
    </div>
  );
}
