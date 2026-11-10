"use client";

import Link from "next/link";
import { useEffect, useRef } from "react";

import { Icon, type IconName } from "./icons";
import { GhostButton } from "./ui";

const OPTIONS: { href: string; icon: IconName; title: string; help: string; effect: string; arrow: string }[] = [
  {
    href: "/scan/sale",
    icon: "receipt",
    title: "Sale / Receipt",
    help: "Customer bought items",
    effect: "Stock goes down",
    arrow: "↓",
  },
  {
    href: "/scan",
    icon: "box",
    title: "Stock In / Delivery",
    help: "Items arrived from supplier",
    effect: "Stock goes up",
    arrow: "↑",
  },
];

export function ScanModeSheet({ open, onClose }: { open: boolean; onClose: () => void }) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const dialog = ref.current;
    if (!dialog) return;
    if (open && !dialog.open) dialog.showModal();
    if (!open && dialog.open) dialog.close();
  }, [open]);

  return (
    <dialog
      ref={ref}
      aria-labelledby="scan-mode-title"
      onCancel={(e) => {
        e.preventDefault();
        onClose();
      }}
      onClick={(e) => {
        if (e.target === ref.current) onClose();
      }}
      className="mx-auto mt-auto mb-0 w-full max-w-lg rounded-t-card bg-background text-text backdrop:bg-dark/40"
    >
      <div className="flex flex-col gap-3 p-5">
        <h2 id="scan-mode-title" className="text-lg font-bold">
          What are you scanning?
        </h2>
        {OPTIONS.map((o) => (
          <Link
            key={o.href}
            href={o.href}
            onClick={onClose}
            className="flex min-h-[96px] items-center gap-4 rounded-card border border-line p-4 hover:bg-surface"
          >
            <span className="grid h-12 w-12 shrink-0 place-items-center rounded-full bg-surface text-accent-text">
              <Icon name={o.icon} size={26} />
            </span>
            <span className="min-w-0">
              <b className="block text-base text-text">{o.title}</b>
              <span className="mt-0.5 block text-sm text-muted">{o.help}</span>
              <span className="mt-0.5 block text-sm font-semibold text-text">
                {o.effect} <span aria-hidden>{o.arrow}</span>
              </span>
            </span>
          </Link>
        ))}
        <GhostButton type="button" onClick={onClose}>
          Cancel
        </GhostButton>
      </div>
    </dialog>
  );
}
