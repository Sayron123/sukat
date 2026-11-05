import { formatQty, pesosToCentavos } from "@/lib/format";
import type { CheckReason, ReviewLine } from "@/lib/types";

import type { PickedProduct } from "./product-picker";

/** One line as the user edits it on the review screen (all inputs are text). */
export type EditLine = {
  key: number; // stable React key
  scanLine: number; // index in the scan, for alias learning on the server
  rawText: string;
  product: PickedProduct | null;
  newProduct: { name: string; category: string; base_unit: string } | null;
  qty: string;
  unit: string;
  price: string; // pesos, as typed
  checkReasons: CheckReason[];
  touched: boolean; // edited by the user: the "Check" tag goes away
  // Sales: the product's usual price for this unit (centavos), for "Price differs".
  // Cleared when the product or unit changes (then it's no longer known here).
  expectedPrice: number | null;
  // True while the price is the product's own price (not written, not edited). Such a
  // line is SAVED WITHOUT a price so the server applies the exact default: the shown
  // price is rounded to the centavo (₱0.09/g) and qty x rounded price would be off.
  priceFromProduct: boolean;
  // The server's exact line total, used until qty, unit, price or product changes.
  // (For small units the server's total is more exact than qty x rounded price.)
  serverTotal: number | null;
};

export const QTY_RE = /^\d{1,9}(\.\d{1,3})?$/;

export function toEditLine(line: ReviewLine, index: number): EditLine {
  return {
    key: index,
    scanLine: index,
    rawText: line.raw_text,
    product:
      line.product_id && line.product_name && line.base_unit
        ? {
            id: line.product_id,
            name: line.product_name,
            base_unit: line.base_unit,
            price_centavos: null, // not needed: the server already filled the line's price
          }
        : null,
    newProduct: line.is_new
      ? { name: line.suggested_new_name ?? "", category: "Others", base_unit: line.unit }
      : null,
    // formatQty only trims zeros after a decimal point ("10.000" -> "10", "10" stays "10").
    qty: line.qty === null ? "" : formatQty(line.qty),
    unit: line.unit,
    price: line.unit_price_centavos === null ? "" : (line.unit_price_centavos / 100).toFixed(2),
    checkReasons: line.check_reasons,
    touched: false,
    expectedPrice: line.expected_unit_price_centavos,
    priceFromProduct: line.price_source === "product",
    serverTotal: line.line_total_centavos,
  };
}

/**
 * Apply an edit. Changing the product or unit forgets the usual price; any change to
 * what the total depends on forgets the server's total.
 */
export function editLine(line: EditLine, patch: Partial<EditLine>): EditLine {
  const next = { ...line, ...patch, touched: true };
  const productChanged = "product" in patch && patch.product?.id !== line.product?.id;
  const unitChanged = "unit" in patch && patch.unit !== line.unit;
  if (productChanged || unitChanged || "newProduct" in patch) next.expectedPrice = null;
  if (productChanged || unitChanged || "qty" in patch || "price" in patch) next.serverTotal = null;
  if ("price" in patch) {
    next.priceFromProduct = patch.priceFromProduct ?? false; // typed by hand
  } else if ((productChanged || unitChanged) && line.priceFromProduct) {
    // The default was for the old product/unit: drop it; the server fills the new one.
    next.price = "";
    next.priceFromProduct = false;
  }
  return next;
}

/** The price to send: none for a product-default price (the server applies it exactly). */
export function priceToSend(line: EditLine): number | null {
  if (line.priceFromProduct) return null;
  return pesosToCentavos(line.price) ?? null;
}

/** Sales: a typed price that isn't the product's usual price for this unit. */
export function priceDiffers(line: EditLine): boolean {
  const price = pesosToCentavos(line.price);
  return line.expectedPrice !== null && typeof price === "number" && price !== line.expectedPrice;
}

/** Line total in centavos for display, or null if qty/price aren't valid numbers yet. */
export function lineTotal(line: EditLine): number | null {
  if (line.serverTotal !== null) return line.serverTotal;
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
  no_unit: "No unit written",
  unknown_unit: "Unit not known for this product",
  qty_too_small: "Quantity too small",
};
