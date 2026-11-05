import type { MovementKind, TransactionType } from "./types";

/** Row titles for transactions and stock movements. */
export const TXN_TITLE: Record<TransactionType, string> = {
  sale: "Sale",
  stock_in: "Stock received",
  adjustment: "Stock adjustment",
};

/** Short type badges. */
export const TXN_BADGE: Record<TransactionType, string> = {
  sale: "Sale",
  stock_in: "Stock in",
  adjustment: "Adjustment",
};

export const KIND_TITLE: Record<MovementKind, string> = { ...TXN_BADGE, void: "Voided" };
