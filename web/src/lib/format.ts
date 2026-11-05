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
  const m = /^(\d{1,8})(?:\.(\d{1,2}))?$/.exec(text);
  if (!m) return undefined;
  return Number(m[1]) * 100 + Number((m[2] ?? "").padEnd(2, "0"));
}

/** 125050 -> "1250.50" for a form field. */
export function centavosToInput(centavos: number | null): string {
  if (centavos === null) return "";
  return `${Math.trunc(centavos / 100)}.${String(centavos % 100).padStart(2, "0")}`;
}
