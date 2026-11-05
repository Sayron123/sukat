"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";

import { Button, Card, GhostButton } from "@/components/ui";
import { ApiError, api } from "@/lib/api-client";
import { compressImage } from "@/lib/compress-image";
import { formatPeso, formatQty, pesosToCentavos } from "@/lib/format";
import { newRequestId } from "@/lib/request-id";
import { canEditProducts, type Me, type Scan, type Transaction, type UploadUrl } from "@/lib/types";

import { type EditLine, lineProblem, lineTotal, toEditLine } from "./lines";
import { ReviewLineCard } from "./review-line";

type Step =
  | { name: "pick"; error?: string }
  | { name: "uploading" }
  | { name: "reading"; photoKey: string; scanId?: string; error?: string }
  | { name: "failed"; scan: Scan }
  | { name: "review"; scan: Scan }
  | { name: "done"; txn: Transaction };

const POLL_MS = 3000;

/**
 * Scan Stock In: photo -> compress -> upload -> AI reads -> review/edit -> save.
 *
 * Saving uses a client_request_id made once per review, so pressing Save again after a
 * dropped connection can never add the stock twice.
 */
export function ScanFlow() {
  const [step, setStep] = useState<Step>({ name: "pick" });
  const [me, setMe] = useState<Me | null>(null);

  useEffect(() => {
    api<Me>("auth/me").then(setMe, () => {});
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
      const scan = await api<Scan>("scans", { method: "POST", body: JSON.stringify({ photo_key: photoKey, type: "stock_in" }) });
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
      return <PickPhoto error={step.error} onFile={startWithFile} />;
    case "uploading":
      return <Busy title="Uploading photo…" />;
    case "reading":
      return (
        <Busy
          title="Reading list…"
          note="This can take up to a minute."
          error={step.error}
          onRetry={step.error ? () => read(step.photoKey) : undefined}
          onCancel={() => setStep({ name: "pick" })}
        />
      );
    case "failed":
      return (
        <Card className="flex flex-col gap-3">
          <h1 className="text-xl font-semibold text-text">Couldn’t read the list</h1>
          <p className="text-muted">{step.scan.error_message ?? "Something went wrong."}</p>
          {step.scan.retryable && <Button onClick={() => retry(step.scan)}>Try again</Button>}
          <GhostButton onClick={() => setStep({ name: "pick" })}>Take another photo</GhostButton>
        </Card>
      );
    case "review":
      return (
        <Review
          scan={step.scan}
          canCreate={canEditProducts(me?.role)}
          onSaved={(txn) => setStep({ name: "done", txn })}
          onCancel={() => setStep({ name: "pick" })}
        />
      );
    case "done":
      return <Done txn={step.txn} onAgain={() => setStep({ name: "pick" })} />;
  }
}

function PickPhoto({ error, onFile }: { error?: string; onFile: (f: File) => void }) {
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
        <h1 className="text-2xl font-semibold text-text">Scan stock in</h1>
        <p className="mt-1 text-sm text-muted">
          Take a photo of the delivery list. Lay it flat, fill the frame, and avoid shadows.
        </p>
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
  canCreate,
  onSaved,
  onCancel,
}: {
  scan: Scan;
  canCreate: boolean;
  onSaved: (txn: Transaction) => void;
  onCancel: () => void;
}) {
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

  const checks = lines.filter((l) => l.checkReasons.length > 0 && !l.touched).length;
  const total = lines.reduce((sum, l) => sum + (lineTotal(l) ?? 0), 0);
  const blockedNew = !canCreate && lines.some((l) => l.newProduct);

  async function save() {
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
          type: "stock_in",
          scan_id: scan.id,
          lines: lines.map((l) => ({
            ...(l.newProduct
              ? { new_product: { name: l.newProduct.name.trim(), category: l.newProduct.category, base_unit: l.newProduct.base_unit.trim() } }
              : { product_id: l.product!.id }),
            qty: l.qty.trim(),
            unit: l.unit.trim(),
            unit_price_centavos: pesosToCentavos(l.price) ?? null,
            scan_line: l.scanLine,
          })),
        }),
      });
      try {
        sessionStorage.removeItem(`sukat-save-${scan.id}`);
      } catch {}
      onSaved(txn);
    } catch (e) {
      // Same requestId on the next tap: if this save actually went through, the server
      // returns it instead of saving again.
      setError(e instanceof ApiError ? e.message : "Could not save. Check your connection and tap Save again.");
      setSaving(false);
    }
  }

  return (
    <div className="flex flex-col gap-4 pb-28">
      <div>
        <h1 className="text-2xl font-semibold text-text">Check the list</h1>
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
          <Button className="w-full" disabled={saving} onClick={save}>
            {saving ? "Saving…" : `Save stock in${total ? ` · ${formatPeso(total)}` : ""}`}
          </Button>
        </div>
      </div>
    </div>
  );
}

function Done({ txn, onAgain }: { txn: Transaction; onAgain: () => void }) {
  return (
    <div className="flex flex-col gap-4">
      <Card role="status" className="text-center">
        <p className="text-lg font-semibold text-green">Stock saved</p>
        <p className="mt-1 text-sm text-muted">
          {txn.items.length} item{txn.items.length === 1 ? "" : "s"}
          {txn.total_centavos > 0 && ` · ${formatPeso(txn.total_centavos)}`}
        </p>
      </Card>
      <Card padded={false}>
        <ul className="divide-y divide-border">
          {txn.items.map((item) => (
            <li key={item.line_no} className="flex items-center justify-between gap-3 px-4 py-3">
              <div className="min-w-0">
                <p className="font-medium text-text">{item.product_name}</p>
                <p className="text-sm text-muted">
                  +{formatQty(item.qty)} {item.unit}
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
      <Button onClick={onAgain}>Scan another list</Button>
      <Link
        href="/stock"
        className="flex h-11 items-center justify-center rounded-button border border-border bg-background text-sm font-medium text-text hover:bg-surface"
      >
        Go to stock
      </Link>
    </div>
  );
}
