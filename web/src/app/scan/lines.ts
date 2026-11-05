import { formatQty, pesosToCentavos } from "@/lib/format";
import type { CheckReason, ReviewLine } from "@/lib/types";

/** One line as the user edits it on the review screen (all inputs are text). */
export type EditLine = {
  key: number; // stable React key
  scanLine: number; // index in the scan, for alias learning on the server
  rawText: string;
  product: { id: string; name: string; base_unit: string } | null;
  newProduct: { name: string; category: string; base_unit: string } | null;
  qty: string;
  unit: string;
  price: string; // pesos, as typed
  checkReasons: CheckReason[];
  touched: boolean; // edited by the user: the "Check" tag goes away
};

export const QTY_RE = /^\d{1,9}(\.\d{1,3})?$/;

export function toEditLine(line: ReviewLine, index: number): EditLine {
  return {
    key: index,
    scanLine: index,
    rawText: line.raw_text,
    product:
      line.product_id && line.product_name && line.base_unit
        ? { id: line.product_id, name: line.product_name, base_unit: line.base_unit }
        : null,
    newProduct: line.is_new
      ? { name: line.suggested_new_name ?? "", category: "Others", base_unit: line.unit || "pc" }
      : null,
    // formatQty only trims zeros after a decimal point ("10.000" -> "10", "10" stays "10").
    qty: line.qty === null ? "" : formatQty(line.qty),
    unit: line.unit,
    price: line.unit_price_centavos === null ? "" : (line.unit_price_centavos / 100).toFixed(2),
    checkReasons: line.check_reasons,
    touched: false,
  };
}

/** Line total in centavos for display, or null if qty/price aren't valid numbers yet. */
export function lineTotal(line: EditLine): number | null {
  const price = pesosToCentavos(line.price);
  if (!QTY_RE.test(line.qty) || price === null || price === undefined) return null;
  return Math.round(Number(line.qty) * price);
}

/** First problem that blocks saving this line, or null if it can be saved. */
export function lineProblem(line: EditLine): string | null {
  if (!line.product && !line.newProduct) return "Pick a product";
  if (line.newProduct && !line.newProduct.name.trim()) return "Enter the new product's name";
  if (line.newProduct && !line.newProduct.base_unit.trim()) return "Enter the new product's unit";
  if (!QTY_RE.test(line.qty.trim()) || Number(line.qty) <= 0) return "Enter a quantity";
  if (!line.unit.trim()) return "Enter a unit";
  if (pesosToCentavos(line.price) === undefined) return "Price must be a number like 250.50";
  return null;
}

export const REASON_TEXT: Record<CheckReason, string> = {
  low_confidence: "Hard to read",
  new_product: "Not in your products",
  no_product: "No matching product",
  no_qty: "Quantity unclear",
  unknown_unit: "Unit not known for this product",
  qty_too_small: "Quantity too small",
};
