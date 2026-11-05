"use client";

import { useEffect, useState } from "react";

import { ConfirmDialog } from "@/components/confirm-dialog";
import { PageHeader } from "@/components/page-header";
import { Button, Loading, Notice } from "@/components/ui";
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

  if (!txn)
    return error ? (
      <>
        <PageHeader title="History" back="/transactions" />
        <p className="text-red">{error}</p>
      </>
    ) : (
      <Loading />
    );

  const isSale = txn.type === "sale";
  const voided = txn.status === "voided";
  const canVoid = !voided && canEditProducts(me?.role);
  const sign = isSale ? "−" : "+";

  return (
    <>
      <PageHeader eyebrow={formatWhen(txn.created_at)} title={isSale ? "Sale" : "Stock received"} back="/transactions" />

      <div className="mb-5 rounded-card bg-surface p-4">
        <p className="text-sm text-muted">{isSale ? "Total" : "Stock value"}</p>
        <strong className={`mt-2 block text-[32px] leading-tight ${voided ? "text-subtle line-through" : "text-text"}`}>
          {formatPeso(txn.total_centavos)}
        </strong>
        <p className="mt-2 text-sm text-muted">
          {txn.items.length} item{txn.items.length === 1 ? "" : "s"}
          {txn.created_by_name && ` · by ${txn.created_by_name}`}
        </p>
      </div>

      {voided && (
        <Notice role="status" icon="history" title="Voided" className="mb-5">
          {txn.voided_at && `${formatWhen(txn.voided_at)}`}
          {txn.voided_by_name && ` by ${txn.voided_by_name}`}. Stock was put back.
        </Notice>
      )}

      <ul className="mb-6 border-t border-border">
        {txn.items.map((item) => (
          <li key={item.line_no} className="flex min-h-[72px] items-center justify-between gap-3 border-b border-border py-2.5">
            <div className="min-w-0">
              <b className="block text-base text-text">{item.product_name}</b>
              <small className="mt-1 block text-sm text-muted">
                {sign} {formatQty(item.qty)} {item.unit}
                {item.unit_price_centavos !== null && ` × ${formatPeso(item.unit_price_centavos)}`}
                {item.unit !== item.base_unit && ` (${formatQty(item.qty_base)} ${item.base_unit})`}
              </small>
            </div>
            <strong className="shrink-0 text-base text-text">
              {item.line_total_centavos === null ? "—" : formatPeso(item.line_total_centavos)}
            </strong>
          </li>
        ))}
      </ul>

      {error && (
        <p role="alert" className="mb-3 text-sm text-red">
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
    </>
  );
}
