"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";

import { Button, Card, GhostButton } from "@/components/ui";
import { ApiError, api } from "@/lib/api-client";
import { compressImage } from "@/lib/compress-image";
import { formatPeso, formatQty } from "@/lib/format";
import { newRequestId } from "@/lib/request-id";
import { takePendingPhoto } from "@/lib/pending-photo";
import {
  canEditProducts,
  type Me,
  type NegativeStockItem,
  type Scan,
  type ScanMode,
  type Transaction,
  type UploadUrl,
} from "@/lib/types";

import { type EditLine, lineProblem, lineTotal, priceToSend, toEditLine } from "./lines";
import { ConfirmDialog } from "@/components/confirm-dialog";

import { ReviewLineCard } from "./review-line";

/** Words that differ between a delivery (stock in) and a sale. */
const TEXT = {
  stock_in: {
    title: "Scan stock in",
    pickHelp: "Take a photo of the delivery list. Lay it flat, fill the frame, and avoid shadows.",
    reading: "Reading list…",
    readFailed: "Couldn’t read the list",
    review: "Check the list",
    save: "Save stock in",
    saved: "Stock saved",
    again: "Scan another list",
  },
  sale: {
    title: "Scan receipt",
    pickHelp: "Take a photo of the sales receipt or order slip. Lay it flat and fill the frame.",
    reading: "Reading receipt…",
    readFailed: "Couldn’t read the receipt",
    review: "Check the sale",
    save: "Save sale",
    saved: "Sale saved",
    again: "Scan another receipt",
  },
} as const;

type Step =
  | { name: "pick"; error?: string }
  | { name: "uploading" }
  | { name: "reading"; photoKey: string; scanId?: string; error?: string }
  | { name: "failed"; scan: Scan }
  | { name: "review"; scan: Scan }
  | { name: "done"; txn: Transaction };

const POLL_MS = 3000;

/**
 * Scan flow for both modes: photo -> compress -> upload -> AI reads -> review -> save.
 * "stock_in" adds stock (new products allowed for managers/secretaries); "sale" removes
 * stock (existing products only, prices default to the product's price).
 *
 * Saving uses a client_request_id made once per review, so pressing Save again after a
 * dropped connection can never save twice.
 */
export function ScanFlow({ mode }: { mode: ScanMode }) {
  const text = TEXT[mode];
  const [step, setStep] = useState<Step>({ name: "pick" });
  const [me, setMe] = useState<Me | null>(null);

  useEffect(() => {
    api<Me>("auth/me").then(setMe, () => {});
  }, []);

  // A photo taken from the home page's "Scan Receipt" button: start with it right away.
  useEffect(() => {
    const file = takePendingPhoto();
    if (file) void startWithFile(file);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- run once on arrival
  }, []);

  async function startWithFile(file: File) {
    setStep({ name: "uploading" });
    let photoKey: string;
    try {
      const photo = await compressImage(file);
      const up = await api<UploadUrl>("scans/upload-url", {
        method: "POST",
        body: JSON.stringify({ content_type: "image/jpeg", size_bytes: photo.size }),
      });
      const put = await fetch(up.upload_url, { method: up.method, headers: up.headers, body: photo });
      if (!put.ok) throw new Error("Upload failed");
      photoKey = up.photo_key;
    } catch (e) {
      setStep({
        name: "pick",
        error: e instanceof ApiError ? e.message : "Could not upload the photo. Check your connection and try again.",
      });
      return;
    }
    await read(photoKey);
  }

  /** Ask the server to read the photo. Safe to repeat: the same photo returns the same scan. */
  async function read(photoKey: string) {
    setStep({ name: "reading", photoKey });
    try {
      const scan = await api<Scan>("scans", { method: "POST", body: JSON.stringify({ photo_key: photoKey, type: mode }) });
      showScan(scan, photoKey);
    } catch (e) {
      setStep({
        name: "reading",
        photoKey,
        error: e instanceof ApiError && e.status !== 0 ? e.message : "Connection lost while reading.",
      });
    }
  }

  function showScan(scan: Scan, photoKey: string) {
    if (scan.status === "read") setStep({ name: "review", scan });
    else if (scan.status === "failed") setStep({ name: "failed", scan });
    else if (scan.status === "saved") setStep({ name: "pick", error: "This photo was already saved." });
    else setStep({ name: "reading", photoKey, scanId: scan.id }); // still reading: poll
  }

  // While another request is still reading this photo, check back every few seconds.
  const pollingId = step.name === "reading" && !step.error ? step.scanId : undefined;
  const pollingKey = step.name === "reading" ? step.photoKey : "";
  useEffect(() => {
    if (!pollingId) return;
    const t = setTimeout(async () => {
      try {
        showScan(await api<Scan>(`scans/${pollingId}`), pollingKey);
      } catch {
        setStep({ name: "reading", photoKey: pollingKey, scanId: pollingId, error: "Connection lost while reading." });
      }
    }, POLL_MS);
    return () => clearTimeout(t);
  }, [pollingId, pollingKey]);

  async function retry(scan: Scan) {
    setStep({ name: "reading", photoKey: "", scanId: scan.id });
    try {
      const again = await api<Scan>(`scans/${scan.id}/retry`, { method: "POST" });
      showScan(again, "");
    } catch (e) {
      setStep({ name: "failed", scan: { ...scan, error_message: e instanceof ApiError ? e.message : "Retry failed", retryable: true } });
    }
  }

  switch (step.name) {
    case "pick":
      return <PickPhoto title={text.title} help={text.pickHelp} error={step.error} onFile={startWithFile} />;
    case "uploading":
      return <Busy title="Uploading photo…" />;
    case "reading":
      return (
        <Busy
          title={text.reading}
          note="This can take up to a minute."
          error={step.error}
          onRetry={step.error ? () => read(step.photoKey) : undefined}
          onCancel={() => setStep({ name: "pick" })}
        />
      );
    case "failed":
      return (
        <Card className="flex flex-col gap-3">
          <h1 className="text-xl font-semibold text-text">{text.readFailed}</h1>
          <p className="text-muted">{step.scan.error_message ?? "Something went wrong."}</p>
          {step.scan.retryable && <Button onClick={() => retry(step.scan)}>Try again</Button>}
          <GhostButton onClick={() => setStep({ name: "pick" })}>Take another photo</GhostButton>
        </Card>
      );
    case "review":
      return (
        <Review
          scan={step.scan}
          mode={mode}
          canCreate={mode === "stock_in" && canEditProducts(me?.role)}
          onSaved={(txn) => setStep({ name: "done", txn })}
          onCancel={() => setStep({ name: "pick" })}
        />
      );
    case "done":
      return <Done txn={step.txn} mode={mode} onAgain={() => setStep({ name: "pick" })} />;
  }
}

function PickPhoto({
  title,
  help,
  error,
  onFile,
}: {
  title: string;
  help: string;
  error?: string;
  onFile: (f: File) => void;
}) {
  const camera = useRef<HTMLInputElement>(null);
  const gallery = useRef<HTMLInputElement>(null);
  const take = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    e.target.value = ""; // allow picking the same file again
    if (file) onFile(file);
  };
  return (
    <div className="flex flex-col gap-4">
      <div>
        <h1 className="text-2xl font-semibold text-text">{title}</h1>
        <p className="mt-1 text-sm text-muted">{help}</p>
      </div>
      {error && (
        <p role="alert" className="rounded-button bg-red/10 px-3 py-2 text-sm text-red">
          {error}
        </p>
      )}
      <input ref={camera} type="file" accept="image/*" capture="environment" className="hidden" onChange={take} />
      <input ref={gallery} type="file" accept="image/*" className="hidden" onChange={take} />
      <Button className="h-14 text-base" onClick={() => camera.current?.click()}>
        Take photo
      </Button>
      <GhostButton onClick={() => gallery.current?.click()}>Choose from gallery</GhostButton>
    </div>
  );
}

function Busy({
  title,
  note,
  error,
  onRetry,
  onCancel,
}: {
  title: string;
  note?: string;
  error?: string;
  onRetry?: () => void;
  onCancel?: () => void;
}) {
  return (
    <Card className="flex flex-col items-center gap-4 py-10 text-center" aria-live="polite">
      {!error && (
        <span
          aria-hidden
          className="h-10 w-10 animate-spin rounded-full border-4 border-border border-t-accent"
        />
      )}
      <p className="text-lg font-semibold text-text">{error ? "Still not read" : title}</p>
      {error ? <p className="text-sm text-red">{error}</p> : note && <p className="text-sm text-muted">{note}</p>}
      {onRetry && <Button onClick={onRetry}>Retry</Button>}
      {onCancel && (
        <button type="button" onClick={onCancel} className="text-sm font-medium text-accent hover:underline">
          Start over
        </button>
      )}
    </Card>
  );
}

function Review({
  scan,
  mode,
  canCreate,
  onSaved,
  onCancel,
}: {
  scan: Scan;
  mode: ScanMode;
  canCreate: boolean;
  onSaved: (txn: Transaction) => void;
  onCancel: () => void;
}) {
  const text = TEXT[mode];
  const [lines, setLines] = useState<EditLine[]>(() => scan.lines.map(toEditLine));
  // One id per review. Kept in sessionStorage so a page reload mid-save reuses it.
  const [requestId] = useState(() => {
    const k = `sukat-save-${scan.id}`;
    try {
      const saved = sessionStorage.getItem(k);
      if (saved) return saved;
      const id = newRequestId();
      sessionStorage.setItem(k, id);
      return id;
    } catch {
      return newRequestId();
    }
  });
  const [showErrors, setShowErrors] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // Set when the server says this sale would take stock below 0.
  const [negative, setNegative] = useState<NegativeStockItem[] | null>(null);

  const checks = lines.filter((l) => l.checkReasons.length > 0 && !l.touched).length;
  const total = lines.reduce((sum, l) => sum + (lineTotal(l) ?? 0), 0);
  const blockedNew = !canCreate && lines.some((l) => l.newProduct);

  /**
   * Send the save. `confirm` is true only after the user accepted the negative-stock
   * warning; the same requestId is reused, which is safe because the refused attempt
   * saved nothing.
   */
  async function save(confirm = false) {
    setShowErrors(true);
    if (lines.length === 0) return setError("Add at least one line, or start over.");
    if (lines.some((l) => lineProblem(l))) return setError("Fix the lines marked in red.");
    if (blockedNew) return setError("Only a manager or secretary can add new products. Pick existing products or remove those lines.");
    setError(null);
    setSaving(true);
    try {
      const txn = await api<Transaction>("transactions", {
        method: "POST",
        body: JSON.stringify({
          client_request_id: requestId,
          type: mode,
          scan_id: scan.id,
          confirm,
          lines: lines.map((l) => ({
            ...(l.newProduct
              ? { new_product: { name: l.newProduct.name.trim(), category: l.newProduct.category, base_unit: l.newProduct.base_unit.trim() } }
              : { product_id: l.product!.id }),
            qty: l.qty.trim(),
            unit: l.unit.trim(),
            unit_price_centavos: priceToSend(l),
            scan_line: l.scanLine,
          })),
        }),
      });
      try {
        sessionStorage.removeItem(`sukat-save-${scan.id}`);
      } catch {}
      setNegative(null);
      onSaved(txn);
    } catch (e) {
      setSaving(false);
      if (e instanceof ApiError && e.code === "negative_stock") {
        setNegative((e.body as { products: NegativeStockItem[] }).products);
        return;
      }
      setNegative(null);
      // Same requestId on the next tap: if this save actually went through, the server
      // returns it instead of saving again.
      setError(e instanceof ApiError ? e.message : "Could not save. Check your connection and tap Save again.");
    }
  }

  return (
    <div className="flex flex-col gap-4 pb-28">
      <div>
        <h1 className="text-2xl font-semibold text-text">{text.review}</h1>
        <p className="mt-1 text-sm text-muted">
          {lines.length} line{lines.length === 1 ? "" : "s"}
          {checks > 0 && <span className="text-amber"> · {checks} to check</span>}
        </p>
      </div>
      {lines.length === 0 && <Card className="text-muted">No items were found on this photo.</Card>}
      <ul className="flex flex-col gap-3">
        {lines.map((line, i) => (
          <ReviewLineCard
            key={line.key}
            line={line}
            index={i}
            canCreate={canCreate}
            isSale={mode === "sale"}
            showErrors={showErrors}
            onChange={(next) => setLines(lines.map((l) => (l.key === line.key ? next : l)))}
            onRemove={() => setLines(lines.filter((l) => l.key !== line.key))}
          />
        ))}
      </ul>
      <button type="button" onClick={onCancel} className="self-center text-sm font-medium text-accent hover:underline">
        Start over
      </button>

      <div className="fixed inset-x-0 bottom-0 z-10 border-t border-border bg-background p-4">
        <div className="mx-auto flex max-w-2xl flex-col gap-2">
          {error && (
            <p role="alert" className="text-sm text-red">
              {error}
            </p>
          )}
          <Button className="w-full" disabled={saving} onClick={() => save()}>
            {saving ? "Saving…" : `${text.save}${total ? ` · ${formatPeso(total)}` : ""}`}
          </Button>
        </div>
      </div>

      <ConfirmDialog
        open={negative !== null}
        title="Not enough stock recorded"
        confirmLabel="Save anyway"
        busy={saving}
        onConfirm={() => save(true)}
        onCancel={() => setNegative(null)}
      >
        <p>This sale would take these below 0:</p>
        <ul className="mt-2 flex flex-col gap-1">
          {(negative ?? []).map((p) => (
            <li key={p.product_id} className="text-text">
              <span className="font-medium">{p.name}</span>: {formatQty(p.stock)} → {formatQty(p.stock_after)}{" "}
              {p.base_unit}
            </li>
          ))}
        </ul>
        <p className="mt-2">
          Save anyway if the delivery hasn’t been recorded yet. Otherwise go back and check the quantities.
        </p>
      </ConfirmDialog>
    </div>
  );
}

function Done({ txn, mode, onAgain }: { txn: Transaction; mode: ScanMode; onAgain: () => void }) {
  const text = TEXT[mode];
  const sign = mode === "sale" ? "−" : "+";
  return (
    <div className="flex flex-col gap-4">
      <Card role="status" className="text-center">
        <p className="text-lg font-semibold text-green">{text.saved}</p>
        {mode === "sale" ? (
          <>
            <p className="mt-2 text-3xl font-semibold text-text">{formatPeso(txn.total_centavos)}</p>
            <p className="mt-1 text-sm text-muted">
              {txn.items.length} item{txn.items.length === 1 ? "" : "s"}
            </p>
          </>
        ) : (
          <p className="mt-1 text-sm text-muted">
            {txn.items.length} item{txn.items.length === 1 ? "" : "s"}
            {txn.total_centavos > 0 && ` · ${formatPeso(txn.total_centavos)}`}
          </p>
        )}
      </Card>
      <Card padded={false}>
        <ul className="divide-y divide-border">
          {txn.items.map((item) => (
            <li key={item.line_no} className="flex items-center justify-between gap-3 px-4 py-3">
              <div className="min-w-0">
                <p className="font-medium text-text">{item.product_name}</p>
                <p className="text-sm text-muted">
                  {sign}
                  {formatQty(item.qty)} {item.unit}
                  {item.unit !== item.base_unit && ` (${formatQty(item.qty_base)} ${item.base_unit})`}
                </p>
              </div>
              <span className="shrink-0 text-sm text-muted">
                now {formatQty(item.stock_after)} {item.base_unit}
              </span>
            </li>
          ))}
        </ul>
      </Card>
      <Button onClick={onAgain}>{text.again}</Button>
      <Link
        href={`/transactions/${txn.id}`}
        className="flex h-11 items-center justify-center rounded-button border border-border bg-background text-sm font-medium text-text hover:bg-surface"
      >
        View details
      </Link>
      <Link
        href="/stock"
        className="flex h-11 items-center justify-center rounded-button border border-border bg-background text-sm font-medium text-text hover:bg-surface"
      >
        Go to stock
      </Link>
    </div>
  );
}
