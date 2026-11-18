"use client";

import { useSyncExternalStore } from "react";

import { currentTheme, currentThemeChoice, setThemeChoice, subscribeTheme, type Theme, type ThemeChoice } from "@/lib/theme";

export function useTheme() {
  const choice = useSyncExternalStore<ThemeChoice>(subscribeTheme, currentThemeChoice, () => "dark");
  const theme = useSyncExternalStore<Theme>(subscribeTheme, currentTheme, () => "dark");
  return { choice, theme, setChoice: setThemeChoice };
}
