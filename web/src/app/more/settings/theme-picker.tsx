"use client";

import { useSyncExternalStore } from "react";

import { Icon, type IconName } from "@/components/icons";
import { Chip } from "@/components/ui";
import { currentThemeChoice, setThemeChoice, subscribeTheme, type ThemeChoice } from "@/lib/theme";

const CHOICES: { value: ThemeChoice; label: string; icon: IconName }[] = [
  { value: "light", label: "Light", icon: "sun" },
  { value: "dark", label: "Dark", icon: "moon" },
  { value: "system", label: "System", icon: "monitor" },
];

export function ThemePicker() {
  const theme = useSyncExternalStore<ThemeChoice>(subscribeTheme, currentThemeChoice, () => "light");

  return (
    <div className="flex gap-2">
      {CHOICES.map((c) => (
        <Chip
          key={c.value}
          selected={theme === c.value}
          aria-label={c.label}
          title={c.label}
          className="grid flex-1 place-items-center"
          onClick={() => setThemeChoice(c.value)}
        >
          <Icon name={c.icon} size={20} />
        </Chip>
      ))}
    </div>
  );
}
