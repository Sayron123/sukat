"use client";

import { useEffect, useRef, useState } from "react";

import { Button, GhostButton } from "@/components/ui";

export type ShareLink = { url: string; title: string; note: string; expiresAt: string };

export function LinkDialog({ link, onClose }: { link: ShareLink | null; onClose: () => void }) {
  const ref = useRef<HTMLDialogElement>(null);
  const [note, setNote] = useState<string | null>(null);

  useEffect(() => {
    const dialog = ref.current;
    if (!dialog) return;
    if (link && !dialog.open) dialog.showModal();
    if (!link && dialog.open) dialog.close();
  }, [link]);

  async function copy(url: string) {
    try {
      await navigator.clipboard.writeText(url);
      setNote("Link copied.");
    } catch {
      setNote("Press and hold the link to copy it.");
    }
  }

  function close() {
    setNote(null);
    onClose();
  }

  const expires = link
    ? new Date(link.expiresAt).toLocaleString("en-PH", {
        month: "long",
        day: "numeric",
        hour: "numeric",
        minute: "2-digit",
      })
    : "";

  return (
    <dialog
      ref={ref}
      aria-labelledby="link-title"
      onCancel={(e) => {
        e.preventDefault();
        close();
      }}
      className="mx-auto mt-auto mb-0 w-full max-w-lg rounded-t-card bg-background text-text backdrop:bg-dark/40"
    >
      {link && (
        <div className="flex flex-col gap-3 p-5 pb-[max(20px,env(safe-area-inset-bottom))]">
          <span aria-hidden className="mx-auto h-1.5 w-10 rounded-full bg-border" />
          <h2 id="link-title" className="text-lg font-bold">
            {link.title}
          </h2>
          <p className="text-sm text-muted">
            {link.note} It works once, until {expires}.
          </p>
          <p className="rounded-button border border-border bg-surface p-3 text-[13px] break-all text-text select-all">
            {link.url}
          </p>
          {note && (
            <p role="status" className="text-sm text-muted">
              {note}
            </p>
          )}
          <Button type="button" size="lg" onClick={() => void copy(link.url)}>
            Copy link
          </Button>
          {typeof navigator !== "undefined" && typeof navigator.share === "function" && (
            <GhostButton
              type="button"
              onClick={() => navigator.share({ title: link.title, url: link.url }).catch(() => {})}
            >
              Share
            </GhostButton>
          )}
          <button type="button" onClick={close} className="grid min-h-11 place-items-center text-[15px] font-semibold">
            Done
          </button>
        </div>
      )}
    </dialog>
  );
}
