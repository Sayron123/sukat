"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { ConfirmDialog } from "@/components/confirm-dialog";
import { Icon } from "@/components/icons";
import { PageHeader } from "@/components/page-header";
import { Badge, Card, Loading } from "@/components/ui";
import { ApiError, api } from "@/lib/api-client";
import { formatShortWhen } from "@/lib/format";
import type { TrashedScan } from "@/lib/types";

const DAY_MS = 24 * 60 * 60 * 1000;

export function RecycleBin() {
  const router = useRouter();
  const [items, setItems] = useState<TrashedScan[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [forever, setForever] = useState<TrashedScan | null>(null);
  const [now] = useState(() => Date.now());

  useEffect(() => {
    api<TrashedScan[]>("scans/trash").then(setItems, (e: unknown) =>
      setError(
        e instanceof ApiError && e.status === 403
          ? "Only managers and secretaries can open the Recycle bin."
          : "Could not load the Recycle bin.",
      ),
    );
  }, []);

  async function restore(item: TrashedScan) {
    setBusy(item.scan_id);
    setError(null);
    try {
      await api(`scans/${item.scan_id}/restore`, { method: "POST" });
      router.push(`/scan/review/${item.scan_id}`);
    } catch (e) {
      setBusy(null);
      setError(e instanceof ApiError ? e.message : "Could not restore it. Please try again.");
    }
  }

  async function deleteForever(item: TrashedScan) {
    setBusy(item.scan_id);
    setError(null);
    try {
      await api(`scans/${item.scan_id}`, { method: "DELETE" });
      setItems((list) => (list ?? []).filter((i) => i.scan_id !== item.scan_id));
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not delete it. Please try again.");
    }
    setBusy(null);
    setForever(null);
  }

  return (
    <>
      <PageHeader
        eyebrow={items ? `${items.length} photo${items.length === 1 ? "" : "s"}` : " "}
        title="Recycle bin"
        back="/scans/review"
      />
      <p className="mb-5 text-sm text-muted">Photos here are deleted for good 30 days after they were moved here.</p>
      {error && (
        <p role="alert" className="mb-4 text-sm text-red">
          {error}
        </p>
      )}
      {items === null ? (
        !error && <Loading />
      ) : items.length === 0 ? (
        <Card className="text-muted">The Recycle bin is empty.</Card>
      ) : (
        <ul className="border-t border-border">
          {items.map((item) => {
            const days = Math.max(0, Math.ceil((Date.parse(item.delete_after) - now) / DAY_MS));
            const name = item.type === "sale" ? "Sale receipt" : "Delivery list";
            return (
              <li key={item.scan_id} className="flex min-h-[88px] items-center gap-3 border-b border-border py-3">
                <span className="grid h-10 w-8 place-items-center text-text">
                  <Icon name={item.type === "sale" ? "receipt" : "box"} size={20} />
                </span>
                <span className="min-w-0 flex-1">
                  <span className="flex flex-wrap items-center gap-x-2 gap-y-1">
                    <b className="text-base text-text">{name}</b>
                    <Badge tone={days <= 3 ? "red" : "neutral"}>{daysLeft(days)}</Badge>
                  </span>
                  <small className="mt-[5px] block text-sm leading-snug text-muted">
                    {item.line_count} line{item.line_count === 1 ? "" : "s"} · deleted {formatShortWhen(item.deleted_at)}
                    {item.deleted_by_name && ` by ${item.deleted_by_name}`}
                  </small>
                </span>
                <button
                  type="button"
                  disabled={busy !== null}
                  onClick={() => restore(item)}
                  className="flex h-10 shrink-0 items-center gap-1.5 rounded-button border border-line bg-background px-3 text-sm font-bold text-text hover:bg-surface disabled:opacity-45"
                >
                  <Icon name="restore" size={18} />
                  Restore
                </button>
                <button
                  type="button"
                  disabled={busy !== null}
                  onClick={() => setForever(item)}
                  aria-label={`Delete this ${name.toLowerCase()} forever`}
                  className="-mr-2 grid h-10 w-10 shrink-0 place-items-center rounded-button text-subtle hover:bg-surface hover:text-red disabled:opacity-45"
                >
                  <Icon name="trash" size={20} />
                </button>
              </li>
            );
          })}
        </ul>
      )}

      <ConfirmDialog
        open={forever !== null}
        title="Delete forever?"
        confirmLabel="Delete forever"
        danger
        busy={busy !== null}
        onConfirm={() => forever && deleteForever(forever)}
        onCancel={() => setForever(null)}
      >
        The photo and everything read from it are deleted right away. This can’t be undone.
      </ConfirmDialog>
    </>
  );
}

function daysLeft(days: number): string {
  if (days === 0) return "Deletes today";
  if (days === 1) return "1 day left";
  return `${days} days left`;
}
