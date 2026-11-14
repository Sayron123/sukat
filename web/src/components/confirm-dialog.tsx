"use client";

import { useEffect, useId, useRef, type ReactNode } from "react";

import { Mascot } from "./mascot";
import { Button, GhostButton } from "./ui";

/**
 * Modal confirm step built on the native <dialog> element (focus trap, Esc to close and
 * screen-reader semantics come with it).
 */
export function ConfirmDialog({
  open,
  title,
  children,
  confirmLabel,
  danger = false,
  busy = false,
  onConfirm,
  onCancel,
}: {
  open: boolean;
  title: string;
  children: ReactNode;
  confirmLabel: string;
  danger?: boolean;
  busy?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  const titleId = useId();
  useEffect(() => {
    const dialog = ref.current;
    if (!dialog) return;
    if (open && !dialog.open) dialog.showModal();
    if (!open && dialog.open) dialog.close();
  }, [open]);

  return (
    <dialog
      ref={ref}
      aria-labelledby={titleId}
      onCancel={(e) => {
        e.preventDefault(); // Esc: let the parent decide (keeps state in one place)
        onCancel();
      }}
      className="m-auto w-[calc(100%-2rem)] max-w-sm rounded-card border border-border bg-surface p-6 text-text backdrop:bg-dark/40"
    >
      {danger && <Mascot emote="warning" size={72} alt="" className="mb-2" />}
      <h2 id={titleId} className="text-lg font-bold">
        {title}
      </h2>
      <div className="mt-2 text-sm text-muted">{children}</div>
      <div className="mt-6 flex flex-col gap-2">
        <Button
          type="button"
          disabled={busy}
          onClick={onConfirm}
          variant={danger ? "danger" : "primary"}
        >
          {busy ? "Please wait…" : confirmLabel}
        </Button>
        <GhostButton type="button" disabled={busy} onClick={onCancel}>
          Cancel
        </GhostButton>
      </div>
    </dialog>
  );
}
