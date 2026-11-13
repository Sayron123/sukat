"use client";

import { useSyncExternalStore } from "react";

import { Mascot } from "./mascot";

function subscribe(onChange: () => void) {
  window.addEventListener("online", onChange);
  window.addEventListener("offline", onChange);
  return () => {
    window.removeEventListener("online", onChange);
    window.removeEventListener("offline", onChange);
  };
}

export function OfflineBanner() {
  const offline = useSyncExternalStore(
    subscribe,
    () => !navigator.onLine,
    () => false,
  );
  if (!offline) return null;
  return (
    <div role="status" className="sticky top-0 z-30 border-b border-border bg-surface">
      <div className="mx-auto flex max-w-lg items-center gap-3 px-5 py-2 text-sm">
        <Mascot emote="offline" size={44} alt="" />
        <p className="min-w-0 leading-snug">
          <b className="text-text">No internet.</b>{" "}
          <span className="text-muted">Sukat will work again when you are back online.</span>
        </p>
      </div>
    </div>
  );
}
