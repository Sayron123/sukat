import { STORE_TZ, addDays, storeDate } from "./dates";

/** "₱1,250.50" from 125050 centavos; "No price" when null. */
export function formatPeso(centavos: number | null): string {
  if (centavos === null) return "No price";
  const pesos = Math.trunc(centavos / 100);
  const cents = String(centavos % 100).padStart(2, "0");
  return `₱${pesos.toLocaleString("en-PH")}.${cents}`;
}

/** "12.5" from "12.500"; keeps API decimals as text so nothing is rounded. */
export function formatQty(qty: string): string {
  return qty.includes(".") ? qty.replace(/\.?0+$/, "") : qty;
}

/**
 * Parse what a person types as a price into centavos, without floating point.
 * "1,250.5" -> 125050. Returns null for blank, undefined for invalid input.
 */
export function pesosToCentavos(input: string): number | null | undefined {
  const text = input.replace(/[,\s₱]/g, "");
  if (text === "") return null;
  // Up to ₱9,999,999.99, the API's limit.
  const m = /^(\d{1,7})(?:\.(\d{1,2}))?$/.exec(text);
  if (!m) return undefined;
  return Number(m[1]) * 100 + Number((m[2] ?? "").padEnd(2, "0"));
}

/** 125050 -> "1250.50" for a form field. */
export function centavosToInput(centavos: number | null): string {
  if (centavos === null) return "";
  return `${Math.trunc(centavos / 100)}.${String(centavos % 100).padStart(2, "0")}`;
}

/** "Nov 5, 2026, 5:26 AM" in store time (Asia/Manila), from an ISO timestamp. */
export function formatWhen(iso: string): string {
  return new Date(iso).toLocaleString("en-PH", { timeZone: STORE_TZ, dateStyle: "medium", timeStyle: "short" });
}

/** "10:32 AM" in store time. */
export function formatTime(iso: string): string {
  return new Date(iso).toLocaleTimeString("en-PH", { timeZone: STORE_TZ, hour: "numeric", minute: "2-digit" });
}

/**
 * "Today, 10:32 AM", "Yesterday, 4:20 PM" or "Nov 3, 9:15 AM" (year added if not this
 * year). Store time (Asia/Manila), so every screen and report agree on what "today" is.
 */
/** "3", or "50+" when the list was cut and there are more than shown. */
export function formatCount(n: number, more: boolean): string {
  return more ? `${n}+` : String(n);
}

export function formatShortWhen(iso: string, now: Date = new Date()): string {
  const d = new Date(iso);
  const time = formatTime(iso);
  const day = storeDate(d);
  const today = storeDate(now);
  if (day === today) return `Today, ${time}`;
  if (day === addDays(today, -1)) return `Yesterday, ${time}`;
  const date = d.toLocaleDateString("en-PH", {
    timeZone: STORE_TZ,
    month: "short",
    day: "numeric",
    year: day.slice(0, 4) === today.slice(0, 4) ? undefined : "numeric",
  });
  return `${date}, ${time}`;
}
