"use client";

import { useSyncExternalStore } from "react";

import { Icon, type IconName } from "@/components/icons";
import { currentThemeChoice, setThemeChoice, subscribeTheme, type ThemeChoice } from "@/lib/theme";

const CHOICES: { value: ThemeChoice; label: string; icon: IconName }[] = [
  { value: "light", label: "Light", icon: "sun" },
  { value: "dark", label: "Dark", icon: "moon" },
  { value: "system", label: "System", icon: "monitor" },
];

export function ThemePicker() {
  const theme = useSyncExternalStore<ThemeChoice>(subscribeTheme, currentThemeChoice, () => "light");

  return (
    <div role="group" aria-label="Appearance" className="flex gap-1 rounded-card border border-border bg-surface p-1">
      {CHOICES.map((c) => {
        const on = theme === c.value;
        return (
          <button
            key={c.value}
            type="button"
            aria-pressed={on}
            onClick={() => setThemeChoice(c.value)}
            className={`flex h-11 flex-1 items-center justify-center gap-1.5 rounded-button text-sm font-semibold ${
              on ? "bg-text text-inverse" : "text-text hover:bg-background"
            }`}
          >
            <Icon name={c.icon} size={18} />
            {c.label}
          </button>
        );
      })}
    </div>
  );
}
