"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useEffectEvent, useRef, useState } from "react";

import { ActionDock } from "@/components/action-dock";
import { ConfirmDialog } from "@/components/confirm-dialog";
import { Icon } from "@/components/icons";
import { PageHeader } from "@/components/page-header";
import { Button, Card, GhostButton, Notice, ghostButtonClass, textLinkClass } from "@/components/ui";
import { ApiError, api } from "@/lib/api-client";
import { compressImage } from "@/lib/compress-image";
import { formatPeso, formatQty } from "@/lib/format";
import { newRequestId } from "@/lib/request-id";
import { watchPendingPhoto } from "@/lib/pending-photo";
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
import { ReviewLineCard } from "./review-line";

/** Words that differ between a delivery (stock in) and a sale. */
const TEXT = {
  stock_in: {
    title: "Scan stock in",
    pickHelp: "Lay the list flat and avoid shadows",
    exit: "/stock",
    other: { label: "SALE", name: "sale", href: "/scan/sale" },
    reading: "Reading list…",
    readFailed: "Couldn’t read the list",
    review: "Review stock in",
    totalLabel: "Stock value",
    save: "Save Stock In",
    saved: "Stock saved",
    again: "Scan another list",
  },
  sale: {
    title: "Scan receipt",
    pickHelp: "Lay the receipt flat and avoid shadows",
    exit: "/",
    other: { label: "STOCK IN", name: "stock in", href: "/scan" },
    reading: "Reading receipt…",
    readFailed: "Couldn’t read the receipt",
    review: "Review sale",
    totalLabel: "Total",
    save: "Save Sale",
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
export function ScanFlow({
  mode,
  initialScan,
  exitHref,
}: {
  mode: ScanMode;
  /** Open an already-read scan straight on its review (from "Needs review"). */
  initialScan?: Scan;
  /** Where "back" on the review goes instead of the camera. */
  exitHref?: string;
}) {
  const text = TEXT[mode];
  const router = useRouter();
  const [step, setStep] = useState<Step>(() => {
    if (!initialScan) return { name: "pick" };
    if (initialScan.status === "read") return { name: "review", scan: initialScan };
    if (initialScan.status === "failed") return { name: "failed", scan: initialScan };
    return { name: "pick", error: initialScan.status === "saved" ? "This photo was already saved." : undefined };
  });
  const [me, setMe] = useState<Me | null>(null);

  useEffect(() => {
    api<Me>("auth/me").then(setMe, () => {});
  }, []);

  // A photo taken with the home page's "Scan Receipt" button: start with it right away,
  // whether this page just mounted or was still alive from an earlier visit.
  const onPendingPhoto = useEffectEvent((file: File) => void startWithFile(file));
  useEffect(() => watchPendingPhoto(onPendingPhoto), []);

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
      return <PickPhoto mode={mode} error={step.error} onFile={startWithFile} />;
    case "uploading":
      return <Busy eyebrow={text.title} title="Uploading photo…" />;
    case "reading":
      return (
        <Busy
          eyebrow={text.title}
          title={text.reading}
          note="This can take up to a minute."
          error={step.error}
          onRetry={step.error ? () => read(step.photoKey) : undefined}
          onCancel={() => setStep({ name: "pick" })}
        />
      );
    case "failed":
      return (
        <>
          <PageHeader eyebrow={text.title} title={text.readFailed} onBack={() => setStep({ name: "pick" })} />
          <Notice icon="spark" title="The photo could not be read">
            {step.scan.error_message ?? "Something went wrong."}
          </Notice>
          <ActionDock>
            {step.scan.retryable && (
              <Button size="lg" onClick={() => retry(step.scan)}>
                Try again
              </Button>
            )}
            <GhostButton onClick={() => setStep({ name: "pick" })}>Take another photo</GhostButton>
          </ActionDock>
        </>
      );
    case "review":
      return (
        <Review
          scan={step.scan}
          mode={mode}
          canCreate={mode === "stock_in" && canEditProducts(me?.role)}
          onSaved={(txn) => setStep({ name: "done", txn })}
          onCancel={() => (exitHref ? router.push(exitHref) : setStep({ name: "pick" }))}
        />
      );
    case "done":
      return <Done txn={step.txn} mode={mode} onAgain={() => setStep({ name: "pick" })} />;
  }
}

/**
 * Dark camera screen. The big round button opens the phone's camera app (a file input
 * with `capture`), the small one the gallery. Covers the whole page, including the tabs.
 */
function PickPhoto({ mode, error, onFile }: { mode: ScanMode; error?: string; onFile: (f: File) => void }) {
  const text = TEXT[mode];
  const camera = useRef<HTMLInputElement>(null);
  const gallery = useRef<HTMLInputElement>(null);
  const take = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    e.target.value = ""; // allow picking the same file again
    if (file) onFile(file);
  };
  const round = "grid h-11 w-11 place-items-center rounded-full bg-white/10 text-white";
  return (
    <div className="fixed inset-0 z-30 flex flex-col bg-dark text-white">
      <div className="mx-auto flex w-full max-w-lg flex-1 flex-col">
        <div className="grid h-[88px] grid-cols-[44px_1fr_44px] items-center gap-2 px-4 pt-[18px] pb-2.5">
          <Link href={text.exit} aria-label="Close" className={round}>
            <Icon name="close" />
          </Link>
          <div className="text-center">
            <h1 className="text-base font-bold">{text.title}</h1>
            <p className="mt-[3px] text-[13px] text-[#a8a29e]">Keep the writing inside the frame</p>
          </div>
          <button type="button" aria-label="Choose from gallery" onClick={() => gallery.current?.click()} className={round}>
            <Icon name="image" />
          </button>
        </div>

        <div className="relative mx-4 my-2.5 grid flex-1 place-items-center overflow-hidden rounded-card bg-[#292524]">
          {/* Corner guides */}
          <div aria-hidden className="absolute inset-x-[22px] top-[30px] bottom-[52px]">
            <i className="absolute top-0 left-0 h-[38px] w-[38px] border-t-[3px] border-l-[3px] border-white" />
            <i className="absolute top-0 right-0 h-[38px] w-[38px] border-t-[3px] border-r-[3px] border-white" />
            <i className="absolute bottom-0 left-0 h-[38px] w-[38px] border-b-[3px] border-l-[3px] border-white" />
            <i className="absolute right-0 bottom-0 h-[38px] w-[38px] border-r-[3px] border-b-[3px] border-white" />
          </div>
          <Icon name="receipt" size={56} className="text-[#78716c]" />
          <p
            role={error ? "alert" : undefined}
            className={`absolute inset-x-4 bottom-3.5 mx-auto w-fit rounded-button px-3 py-2 text-center text-[13px] ${
              error ? "bg-red text-white" : "bg-dark/75"
            }`}
          >
            {error ?? text.pickHelp}
          </p>
        </div>

        <input ref={camera} type="file" accept="image/*" capture="environment" className="hidden" onChange={take} />
        <input ref={gallery} type="file" accept="image/*" className="hidden" onChange={take} />
        <div className="grid h-32 grid-cols-[1fr_88px_1fr] items-center px-6 pt-4 pb-7">
          <button
            type="button"
            aria-label="Choose from gallery"
            onClick={() => gallery.current?.click()}
            className="grid h-11 w-11 place-items-center justify-self-center rounded-button bg-[#292524]"
          >
            <Icon name="image" size={20} />
          </button>
          <button
            type="button"
            aria-label="Take photo"
            onClick={() => camera.current?.click()}
            className="group h-[76px] w-[76px] justify-self-center rounded-full border-[3px] border-white p-1.5"
          >
            <span className="block h-full w-full rounded-full bg-white group-active:bg-line" />
          </button>
          <Link
            href={text.other.href}
            aria-label={`Switch to ${text.other.name}`}
            className="justify-self-center rounded-button bg-[#292524] p-2 text-[13px] font-bold"
          >
            {text.other.label}
          </Link>
        </div>
      </div>
    </div>
  );
}

function Busy({
  eyebrow,
  title,
  note,
  error,
  onRetry,
  onCancel,
}: {
  eyebrow: string;
  title: string;
  note?: string;
  error?: string;
  onRetry?: () => void;
  onCancel?: () => void;
}) {
  return (
    <>
      <PageHeader eyebrow={eyebrow} title={error ? "Still not read" : title} onBack={onCancel} />
      <div className="flex flex-col items-center gap-4 py-10 text-center" aria-live="polite">
        {!error && (
          <span aria-hidden className="h-10 w-10 animate-spin rounded-full border-4 border-border border-t-accent" />
        )}
        {error ? <p className="text-sm text-red">{error}</p> : note && <p className="text-sm text-muted">{note}</p>}
      </div>
      {(onRetry || onCancel) && (
        <ActionDock>
          {onRetry && (
            <Button size="lg" onClick={onRetry}>
              Retry
            </Button>
          )}
          {onCancel && (
            <GhostButton type="button" onClick={onCancel}>
              Start over
            </GhostButton>
          )}
        </ActionDock>
      )}
    </>
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
    <>
      <PageHeader
        eyebrow={`${lines.length} item${lines.length === 1 ? "" : "s"} found`}
        title={text.review}
        onBack={onCancel}
      />
      {checks > 0 && (
        <Notice icon="spark" title="Check highlighted items" className="mb-5">
          {checks} line{checks === 1 ? "" : "s"} could not be read clearly.
        </Notice>
      )}
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
      <div className="mt-[22px] flex items-center justify-between border-t-2 border-text pt-[18px]">
        <span className="font-semibold text-text">{text.totalLabel}</span>
        <strong className="text-[25px] text-text">{formatPeso(total)}</strong>
      </div>
      <button type="button" onClick={onCancel} className={`${textLinkClass} mt-2`}>
        Start over
      </button>

      <ActionDock>
        {error && (
          <p role="alert" className="text-sm text-red">
            {error}
          </p>
        )}
        <Button size="lg" disabled={saving} onClick={() => save()}>
          {saving ? "Saving…" : text.save}
        </Button>
      </ActionDock>

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
              <span className="font-bold">{p.name}</span>: {formatQty(p.stock)} → {formatQty(p.stock_after)}{" "}
              {p.base_unit}
            </li>
          ))}
        </ul>
        <p className="mt-2">
          Save anyway if the delivery hasn’t been recorded yet. Otherwise go back and check the quantities.
        </p>
      </ConfirmDialog>
    </>
  );
}

function Done({ txn, mode, onAgain }: { txn: Transaction; mode: ScanMode; onAgain: () => void }) {
  const text = TEXT[mode];
  const sign = mode === "sale" ? "−" : "+";
  return (
    <>
      <PageHeader
        eyebrow={`${txn.items.length} item${txn.items.length === 1 ? "" : "s"}`}
        title={text.saved}
        back={text.exit}
      />
      <div role="status" className="mb-5 flex items-center gap-3 rounded-card bg-surface p-4">
        <span className="grid h-10 w-10 place-items-center rounded-full bg-green text-white">
          <Icon name="check" />
        </span>
        <div>
          <p className="font-bold text-text">{text.saved}</p>
          {txn.total_centavos > 0 && <p className="text-2xl font-bold text-text">{formatPeso(txn.total_centavos)}</p>}
        </div>
      </div>
      <ul className="border-t border-border">
        {txn.items.map((item) => (
          <li key={item.line_no} className="flex min-h-[72px] items-center justify-between gap-3 border-b border-border py-2.5">
            <div className="min-w-0">
              <b className="block text-base text-text">{item.product_name}</b>
              <small className="mt-1 block text-sm text-muted">
                now {formatQty(item.stock_after)} {item.base_unit}
              </small>
            </div>
            <strong className="shrink-0 text-base text-text">
              {sign} {formatQty(item.qty)} {item.unit}
            </strong>
          </li>
        ))}
      </ul>
      <ActionDock>
        <Button size="lg" icon="camera" onClick={onAgain}>
          {text.again}
        </Button>
        <Link href={`/transactions/${txn.id}`} className={ghostButtonClass}>
          View details
        </Link>
      </ActionDock>
    </>
  );
}
