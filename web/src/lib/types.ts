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
