/** Shapes returned by the API (decimals arrive as strings to stay exact). */

export const CATEGORIES = [
  "Cement",
  "Steel",
  "Wood",
  "Nails & Screws",
  "Paint",
  "Electrical",
  "Plumbing",
  "Roofing",
  "Tools",
  "Others",
] as const;
export type Category = (typeof CATEGORIES)[number];

export type Role = "manager" | "secretary" | "member";

export type Me = {
  user_id: string;
  email: string;
  full_name: string;
  store_id: string;
  store_name: string;
  store_address: string | null;
  role: Role;
};

export type Conversion = { from_unit: string; factor: string };

export type Product = {
  id: string;
  name: string;
  category: Category;
  base_unit: string;
  price_centavos: number | null;
  stock_qty: string;
  low_stock_level: string | null;
  is_low_stock: boolean;
  archived: boolean;
  aliases: string[];
  conversions: Conversion[];
  created_at: string;
  updated_at: string;
};

export type ProductPage = {
  items: Product[];
  total: number;
  page: number;
  page_size: number;
  pages: number;
};

export type CatalogItem = {
  key: string;
  name: string;
  category: Category;
  base_unit: string;
  aliases: string[];
  conversions: Conversion[];
  already_in_store: boolean;
};

export type ImportResult = {
  created: number;
  skipped: { key: string; name: string; reason: string }[];
  dropped_aliases: { key: string; alias: string; reason: string }[];
};

export function canEditProducts(role: Role | undefined): boolean {
  return role === "manager" || role === "secretary";
}

export type UploadUrl = {
  photo_key: string;
  upload_url: string;
  method: string;
  headers: Record<string, string>;
  expires_in: number;
};

export type CheckReason =
  | "low_confidence"
  | "new_product"
  | "no_product"
  | "no_qty"
  | "no_unit"
  | "unknown_unit"
  | "qty_too_small";

export type ReviewLine = {
  raw_text: string;
  product_id: string | null;
  product_name: string | null;
  base_unit: string | null;
  suggested_new_name: string | null;
  is_new: boolean;
  qty: string | null;
  unit: string;
  qty_base: string | null;
  unit_price_centavos: number | null;
  price_source: "receipt" | "product" | null;
  expected_unit_price_centavos: number | null;
  line_total_centavos: number | null;
  confidence: number;
  needs_check: boolean;
  check_reasons: CheckReason[];
  warnings: "price_differs"[];
};

export type Scan = {
  id: string;
  type: "sale" | "stock_in";
  status: "pending" | "read" | "failed" | "saved";
  error_message: string | null;
  retryable: boolean;
  model: string | null;
  lines: ReviewLine[];
  created_at: string;
};

export type TransactionItem = {
  line_no: number;
  product_id: string;
  product_name: string;
  base_unit: string;
  qty: string;
  unit: string;
  qty_base: string;
  unit_price_centavos: number | null;
  line_total_centavos: number | null;
  stock_after: string;
};

export type ScanMode = "stock_in" | "sale";

export type Transaction = {
  id: string;
  type: ScanMode;
  status: "saved" | "voided";
  client_request_id: string;
  scan_id: string | null;
  total_centavos: number;
  items: TransactionItem[];
  created_at: string;
  created_by_name: string | null;
  voided_at: string | null;
  voided_by_name: string | null;
};

export type TransactionType = ScanMode | "adjustment";

export type TransactionSummary = {
  id: string;
  type: TransactionType;
  status: "saved" | "voided";
  total_centavos: number;
  item_count: number;
  created_at: string;
};

export type TransactionPage = {
  items: TransactionSummary[];
  total: number;
  page: number;
  page_size: number;
  pages: number;
};

/** Body of a 409 with code "negative_stock" (a sale that would take stock below 0). */
export type NegativeStockItem = {
  product_id: string;
  name: string;
  base_unit: string;
  stock: string;
  stock_after: string;
};

// ---------- Phase 5 reports (api/app/insights/schemas.py) ----------

/** Manila calendar days, both included (YYYY-MM-DD). */
export type DateRange = { start: string; end: string };

export type SalesSummary = {
  range: DateRange;
  total_centavos: number;
  sales_count: number;
  previous: { range: DateRange; total_centavos: number; sales_count: number };
  change_pct: number | null; // null when the previous period had no sales
};

export type LowStockItem = {
  product_id: string;
  name: string;
  category: string;
  base_unit: string;
  stock_qty: string;
  low_stock_level: string;
};

/** What caused a stock movement; "void" undoes a line of a voided transaction. */
export type MovementKind = TransactionType | "void";

export type MovementRow = {
  id: string;
  created_at: string;
  product_id: string;
  product_name: string;
  base_unit: string;
  qty_change: string;
  stock_after: string;
  kind: MovementKind;
  transaction_id: string;
  created_by: string;
  created_by_name: string | null;
};

export type MovementPage = {
  items: MovementRow[];
  total: number;
  page: number;
  page_size: number;
  pages: number;
};

export type ScanToReview = {
  scan_id: string;
  type: ScanMode;
  line_count: number;
  created_at: string;
  created_by_name: string | null;
};
