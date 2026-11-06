/**
 * Store dates. Reports use calendar days in the store's time zone (Asia/Manila), as
 * YYYY-MM-DD strings, whatever time zone the phone is set to.
 */

// Must match STORE_TIMEZONE in api/app/core/config.py: change both together.
export const STORE_TZ = "Asia/Manila";

/** "2026-11-05" for `when` in Manila. */
export function storeDate(when: Date = new Date()): string {
  // en-CA formats as YYYY-MM-DD.
  return new Intl.DateTimeFormat("en-CA", { timeZone: STORE_TZ }).format(when);
}

/** Add days to a YYYY-MM-DD date (calendar math, no time zone involved). */
export function addDays(day: string, days: number): string {
  const d = new Date(`${day}T00:00:00Z`);
  d.setUTCDate(d.getUTCDate() + days);
  return d.toISOString().slice(0, 10);
}

export type RangeKey = "today" | "week" | "month" | "custom";

/**
 * The Manila days for a quick filter. Weeks start on Monday.
 * @param custom used for "custom"; null when incomplete or end is before start
 */
export function rangeFor(
  key: RangeKey,
  custom: { start: string; end: string } = { start: "", end: "" },
  now: Date = new Date(),
): { start: string; end: string } | null {
  const today = storeDate(now);
  if (key === "today") return { start: today, end: today };
  if (key === "week") {
    const weekday = new Date(`${today}T00:00:00Z`).getUTCDay(); // 0 = Sunday
    return { start: addDays(today, -((weekday + 6) % 7)), end: today };
  }
  if (key === "month") return { start: `${today.slice(0, 8)}01`, end: today };
  const { start, end } = custom;
  if (!/^\d{4}-\d{2}-\d{2}$/.test(start) || !/^\d{4}-\d{2}-\d{2}$/.test(end) || end < start) return null;
  return { start, end };
}

/** "Today", "Yesterday" or "Tue, Nov 3" for a YYYY-MM-DD day (for list headings). */
export function dayLabel(day: string, now: Date = new Date()): string {
  const today = storeDate(now);
  if (day === today) return "Today";
  if (day === addDays(today, -1)) return "Yesterday";
  return new Date(`${day}T00:00:00Z`).toLocaleDateString("en-PH", {
    timeZone: "UTC",
    weekday: "short",
    month: "short",
    day: "numeric",
    year: day.slice(0, 4) === today.slice(0, 4) ? undefined : "numeric",
  });
}

/**
 * "6 November", "2–6 November", "28 October – 6 November" (year added when it's not
 * this year), for YYYY-MM-DD days.
 */
export function formatRange(start: string, end: string, now: Date = new Date()): string {
  const year = storeDate(now).slice(0, 4);
  const part = (day: string, withMonth: boolean, withYear: boolean) =>
    new Date(`${day}T00:00:00Z`).toLocaleDateString("en-GB", {
      timeZone: "UTC",
      day: "numeric",
      month: withMonth ? "long" : undefined,
      year: withYear ? "numeric" : undefined,
    });
  const endYear = end.slice(0, 4) !== year;
  if (start === end) return part(end, true, endYear);
  if (start.slice(0, 7) === end.slice(0, 7)) return `${part(start, false, false)}–${part(end, true, endYear)}`;
  const startYear = start.slice(0, 4) !== end.slice(0, 4);
  return `${part(start, true, startYear)} – ${part(end, true, endYear)}`;
}
