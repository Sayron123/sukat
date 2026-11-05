"use client";

import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";

import { ActionDock } from "@/components/action-dock";
import { Icon } from "@/components/icons";
import { PageHeader } from "@/components/page-header";
import { Button, Field, GhostButton, Notice, Select } from "@/components/ui";
import { ApiError, api } from "@/lib/api-client";
import { centavosToInput, formatQty, pesosToCentavos } from "@/lib/format";
import { CATEGORIES, type Product } from "@/lib/types";

const COMMON_UNITS = ["pc", "kg", "bag", "m", "l", "gal", "box", "roll", "sheet", "set", "pair", "can", "cu.m"];
const QTY_PATTERN = /^\d{1,9}(\.\d{1,3})?$/;
const FACTOR_PATTERN = /^\d{1,12}(\.\d{1,6})?$/;

type ConvRow = { from_unit: string; factor: string };

/**
 * Add or edit a product. stock_qty is shown read-only: it only changes through stock
 * movements (later phase), and the API rejects it here anyway.
 */
export function ProductForm({ product }: { product?: Product }) {
  const router = useRouter();
  const [name, setName] = useState(product?.name ?? "");
  const [category, setCategory] = useState<string>(product?.category ?? "Others");
  const [baseUnit, setBaseUnit] = useState(product?.base_unit ?? "pc");
  const [price, setPrice] = useState(centavosToInput(product?.price_centavos ?? null));
  const [lowStock, setLowStock] = useState(product?.low_stock_level ? formatQty(product.low_stock_level) : "");
  const [aliases, setAliases] = useState((product?.aliases ?? []).join(", "));
  const [convs, setConvs] = useState<ConvRow[]>(
    (product?.conversions ?? []).map((c) => ({ from_unit: c.from_unit, factor: formatQty(c.factor) })),
  );
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  function validate(): string | Record<string, unknown> {
    const priceCentavos = pesosToCentavos(price);
    if (priceCentavos === undefined)
      return "Price must be a number like 250 or 1250.50 (up to ₱9,999,999.99)";
    const low = lowStock.trim();
    if (low && !QTY_PATTERN.test(low)) return "Low stock level must be a number (up to 3 decimals)";
    const rows = convs.filter((c) => c.from_unit.trim() || c.factor.trim());
    for (const c of rows) {
      if (!c.from_unit.trim()) return "Each conversion needs a unit";
      if (!FACTOR_PATTERN.test(c.factor.trim()) || Number(c.factor) <= 0)
        return `Conversion for "${c.from_unit}" needs a number above 0`;
    }
    return {
      name,
      category,
      base_unit: baseUnit,
      price_centavos: priceCentavos,
      low_stock_level: low || null,
      aliases: aliases
        .split(",")
        .map((a) => a.trim())
        .filter(Boolean),
      conversions: rows.map((c) => ({ from_unit: c.from_unit.trim(), factor: c.factor.trim() })),
    };
  }

  async function onSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const body = validate();
    if (typeof body === "string") {
      setError(body);
      return;
    }
    setError(null);
    setSaving(true);
    try {
      await api(product ? `products/${product.id}` : "products", {
        method: product ? "PATCH" : "POST",
        body: JSON.stringify(body),
      });
      router.push("/stock");
      router.refresh();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not save");
      setSaving(false);
    }
  }

  async function toggleArchive() {
    if (!product) return;
    if (!product.archived && !window.confirm(`Archive "${product.name}"? It will be hidden from the stock list.`))
      return;
    setSaving(true);
    try {
      await api(`products/${product.id}/${product.archived ? "unarchive" : "archive"}`, { method: "POST" });
      router.push("/stock");
      router.refresh();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not update");
      setSaving(false);
    }
  }

  return (
    <>
      <PageHeader eyebrow="Product details" title={product ? "Edit product" : "Add product"} back="/stock" />

      {product?.archived && (
        <Notice icon="box" title="This product is archived" className="mb-5">
          It is hidden from the stock list. Unarchive it to use it again.
        </Notice>
      )}

      <form id="product-form" onSubmit={onSubmit} method="post" className="flex flex-col gap-[22px]">
        <Field
          id="name"
          label="Product name"
          value={name}
          onChange={(e) => setName(e.target.value)}
          required
          maxLength={160}
        />
        <Select id="category" label="Category" value={category} onChange={(e) => setCategory(e.target.value)}>
          {CATEGORIES.map((c) => (
            <option key={c}>{c}</option>
          ))}
        </Select>
        <Field
          id="base_unit"
          label="Base unit"
          list="units"
          value={baseUnit}
          onChange={(e) => setBaseUnit(e.target.value)}
          required
          maxLength={20}
          hint="The unit you count stock in, e.g. pc, kg, bag."
        />
        <datalist id="units">
          {COMMON_UNITS.map((u) => (
            <option key={u} value={u} />
          ))}
        </datalist>
        <Field
          id="price"
          label={`Selling price per ${baseUnit || "unit"}`}
          prefix="₱"
          inputMode="decimal"
          placeholder="No price"
          value={price}
          onChange={(e) => setPrice(e.target.value)}
        />
        <Field
          id="low_stock"
          label="Low stock alert at"
          suffix={baseUnit}
          inputMode="decimal"
          placeholder="Off"
          value={lowStock}
          onChange={(e) => setLowStock(e.target.value)}
          hint="We’ll warn you when stock reaches this number. Leave blank to turn off."
        />
        {product && (
          <div>
            <p className="mb-[7px] text-[13px] font-bold text-text">In stock</p>
            <p className="text-2xl leading-none font-bold text-text">
              {formatQty(product.stock_qty)} <span className="text-[13px] font-normal text-muted">{product.base_unit}</span>
            </p>
            <p className="mt-1.5 text-[13px] text-subtle">Stock changes through deliveries and sales, not here.</p>
          </div>
        )}
        <Field
          id="aliases"
          label="Other names"
          placeholder="e.g. sem, semento"
          value={aliases}
          onChange={(e) => setAliases(e.target.value)}
          hint="Comma-separated. Helps the scanner and search find this product."
        />

        <section className="border-t border-border pt-5">
          <h2 className="text-[13px] font-bold text-text">Other units</h2>
          <p className="mt-1 text-[13px] leading-snug text-subtle">
            Example: 1 box = 25 {baseUnit || "kg"}. g/kg, ml/l and cm/m are converted automatically.
          </p>
          <div className="mt-3 flex flex-col gap-3">
            {convs.map((c, i) => (
              <div key={i} className="flex items-end gap-2">
                <span className="flex h-[42px] items-center text-sm text-muted">1</span>
                <Field
                  id={`conv-unit-${i}`}
                  compact
                  wrapperClassName="flex-1"
                  label="Unit"
                  value={c.from_unit}
                  onChange={(e) => setConvs(convs.map((x, j) => (j === i ? { ...x, from_unit: e.target.value } : x)))}
                />
                <span className="flex h-[42px] items-center text-sm text-muted">=</span>
                <Field
                  id={`conv-factor-${i}`}
                  compact
                  wrapperClassName="flex-1"
                  label={baseUnit || "base unit"}
                  inputMode="decimal"
                  value={c.factor}
                  onChange={(e) => setConvs(convs.map((x, j) => (j === i ? { ...x, factor: e.target.value } : x)))}
                />
                <button
                  type="button"
                  aria-label={`Remove ${c.from_unit || "unit"}`}
                  onClick={() => setConvs(convs.filter((_, j) => j !== i))}
                  className="grid h-[42px] w-10 shrink-0 place-items-center rounded-button text-muted hover:bg-surface hover:text-red"
                >
                  <Icon name="close" size={18} />
                </button>
              </div>
            ))}
          </div>
          <button
            type="button"
            onClick={() => setConvs([...convs, { from_unit: "", factor: "" }])}
            className="mt-1 flex h-[52px] items-center gap-1.5 text-[13px] font-semibold text-muted"
          >
            <Icon name="plus" size={18} />
            Add unit
          </button>
        </section>

        {product && (
          <GhostButton type="button" onClick={toggleArchive} disabled={saving}>
            {product.archived ? "Unarchive product" : "Archive product"}
          </GhostButton>
        )}
      </form>

      <ActionDock>
        {error && (
          <p role="alert" className="text-sm text-red">
            {error}
          </p>
        )}
        <Button type="submit" form="product-form" size="lg" disabled={saving}>
          {saving ? "Saving…" : "Save Product"}
        </Button>
      </ActionDock>
    </>
  );
}
