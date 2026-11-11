"use client";

import type { ScanMode } from "@/lib/types";

import { Icon, type IconName } from "./icons";

const TYPES: { value: ScanMode; label: string; icon: IconName }[] = [
  { value: "stock_in", label: "Delivery", icon: "box" },
  { value: "sale", label: "Sale", icon: "receipt" },
];

export function ScanTypeSwitch({
  value,
  disabled,
  onChange,
}: {
  value: ScanMode;
  disabled: boolean;
  onChange: (next: ScanMode) => void;
}) {
  return (
    <div role="group" aria-label="What is this photo?" className="inline-grid grid-cols-2 gap-1 rounded-button bg-surface p-1">
      {TYPES.map((t) => (
        <button
          key={t.value}
          type="button"
          aria-pressed={value === t.value}
          disabled={disabled}
          onClick={() => value !== t.value && onChange(t.value)}
          className={`flex h-9 items-center justify-center gap-1.5 rounded-[9px] px-3 text-[13px] font-bold disabled:opacity-60 ${
            value === t.value ? "bg-background text-text shadow-sm" : "text-muted"
          }`}
        >
          <Icon name={t.icon} size={16} />
          {t.label}
        </button>
      ))}
    </div>
  );
}
