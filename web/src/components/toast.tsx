"use client";

import { useEffect, useSyncExternalStore } from "react";

import { Icon } from "./icons";

const SHOWN_MS = 3500;

let message: string | null = null;
const listeners = new Set<() => void>();

function emit(next: string | null) {
  message = next;
  for (const listener of listeners) listener();
}

function subscribe(listener: () => void) {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

export function showToast(text: string) {
  emit(text);
}

export function Toast() {
  const text = useSyncExternalStore(
    subscribe,
    () => message,
    () => null,
  );

  useEffect(() => {
    if (!text) return;
    const timer = setTimeout(() => emit(null), SHOWN_MS);
    return () => clearTimeout(timer);
  }, [text]);

  if (!text) return null;
  return (
    <div className="pointer-events-none fixed inset-x-0 bottom-[calc(var(--nav-h,0px)+16px)] z-30 flex justify-center px-5">
      <p
        role="status"
        className="flex max-w-lg items-center gap-2 rounded-button bg-text px-4 py-3 text-sm font-semibold text-inverse shadow-lg motion-safe:animate-pop-in"
      >
        <Icon name="check" size={18} />
        {text}
      </p>
    </div>
  );
}
