export type ThemeChoice = "light" | "dark" | "system";

const STORAGE_KEY = "sukat-theme";
const LIGHT_BAR = "#ffffff";
const DARK_BAR = "#1c1917";
const BAR_SELECTOR = 'meta[name="theme-color"]';
const DARK_QUERY = "(prefers-color-scheme: dark)";

export const THEME_SCRIPT = `(function(){var m=matchMedia("${DARK_QUERY}");function a(){var c=null;try{c=localStorage.getItem("${STORAGE_KEY}")}catch(e){}var d=c==="dark"||(c==="system"&&m.matches);document.documentElement.dataset.theme=d?"dark":"light";document.querySelector('${BAR_SELECTOR}')?.setAttribute("content",d?"${DARK_BAR}":"${LIGHT_BAR}")}a();m.addEventListener("change",a)})()`;

const listeners = new Set<() => void>();
let choice: ThemeChoice | null = null;

function readChoice(): ThemeChoice {
  try {
    const saved = localStorage.getItem(STORAGE_KEY);
    if (saved === "dark" || saved === "system") return saved;
  } catch {}
  return "light";
}

export function subscribeTheme(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

export function currentThemeChoice(): ThemeChoice {
  choice ??= readChoice();
  return choice;
}

export function setThemeChoice(next: ThemeChoice): void {
  choice = next;
  try {
    localStorage.setItem(STORAGE_KEY, next);
  } catch {}
  const dark = next === "dark" || (next === "system" && matchMedia(DARK_QUERY).matches);
  document.documentElement.dataset.theme = dark ? "dark" : "light";
  document.querySelector(BAR_SELECTOR)?.setAttribute("content", dark ? DARK_BAR : LIGHT_BAR);
  listeners.forEach((listener) => listener());
}
