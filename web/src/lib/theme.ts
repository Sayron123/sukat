export type ThemeChoice = "light" | "dark" | "system";
export type Theme = "light" | "dark";

const STORAGE_KEY = "sukat-theme";
const LIGHT_BAR = "#f5f5f4";
export const DARK_BAR = "#1c1917";
const BAR_SELECTOR = 'meta[name="theme-color"]';
const DARK_QUERY = "(prefers-color-scheme: dark)";

export const THEME_SCRIPT = `(function(){var m=matchMedia("${DARK_QUERY}");function a(){var c=null;try{c=localStorage.getItem("${STORAGE_KEY}")}catch(e){}var d=c==="light"?false:c==="system"?m.matches:true;document.documentElement.dataset.theme=d?"dark":"light";document.querySelector('${BAR_SELECTOR}')?.setAttribute("content",d?"${DARK_BAR}":"${LIGHT_BAR}")}a();m.addEventListener("change",a)})()`;

const listeners = new Set<() => void>();
let choice: ThemeChoice | null = null;

function readChoice(): ThemeChoice {
  try {
    const saved = localStorage.getItem(STORAGE_KEY);
    if (saved === "light" || saved === "system") return saved;
  } catch {}
  return "dark";
}

function resolve(next: ThemeChoice): Theme {
  if (next === "system") return matchMedia(DARK_QUERY).matches ? "dark" : "light";
  return next;
}

export function subscribeTheme(listener: () => void): () => void {
  const media = matchMedia(DARK_QUERY);
  listeners.add(listener);
  media.addEventListener("change", listener);
  return () => {
    listeners.delete(listener);
    media.removeEventListener("change", listener);
  };
}

export function currentThemeChoice(): ThemeChoice {
  choice ??= readChoice();
  return choice;
}

export function currentTheme(): Theme {
  return resolve(currentThemeChoice());
}

export function setThemeChoice(next: ThemeChoice): void {
  choice = next;
  try {
    localStorage.setItem(STORAGE_KEY, next);
  } catch {}
  const dark = resolve(next) === "dark";
  document.documentElement.dataset.theme = dark ? "dark" : "light";
  document.querySelector(BAR_SELECTOR)?.setAttribute("content", dark ? DARK_BAR : LIGHT_BAR);
  listeners.forEach((listener) => listener());
}
