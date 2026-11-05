"use client";

import { Field, Select } from "@/components/ui";
import { formatPeso } from "@/lib/format";
import { CATEGORIES } from "@/lib/types";

import { type EditLine, REASON_TEXT, editLine, lineProblem, lineTotal, priceDiffers } from "./lines";
import { type PickedProduct, ProductPicker } from "./product-picker";

/**
 * One editable line on the review screen.
 * - Amber border + "Check" tag: the AI was unsure (until the user edits the line).
 * - "New" tag: saving will create this product (stock in only).
 * - "Price differs" tag: a sale price that isn't the product's usual price.
 *
 * @param canCreate whether "Add as new product" is offered (stock in + manager/secretary)
 * @param isSale sale mode: prices default to the product's price, no new products
 */
export function ReviewLineCard({
  line,
  index,
  canCreate,
  isSale,
  showErrors,
  onChange,
  onRemove,
}: {
  line: EditLine;
  index: number;
  canCreate: boolean;
  isSale: boolean;
  showErrors: boolean;
  onChange: (next: EditLine) => void;
  onRemove: () => void;
}) {
  const needsCheck = line.checkReasons.length > 0 && !line.touched;
  const differs = isSale && priceDiffers(line);
  const problem = showErrors ? lineProblem(line) : null;
  const total = lineTotal(line);
  const update = (patch: Partial<EditLine>) => onChange(editLine(line, patch));

  function pickProduct(p: PickedProduct) {
    const patch: Partial<EditLine> = { product: p };
    // Sale with no price yet: use the product's price when the unit is its base unit.
    // (For other units the server fills in the converted price when saving.)
    if (isSale && (!line.price.trim() || line.priceFromProduct) && p.price_centavos !== null && line.unit === p.base_unit) {
      patch.price = (p.price_centavos / 100).toFixed(2);
      patch.priceFromProduct = true;
    }
    update(patch);
  }
  const id = (name: string) => `line-${line.key}-${name}`;

  return (
    <li
      aria-label={`Line ${index + 1}`}
      className={`rounded-card border-2 bg-surface p-4 ${
        problem ? "border-red" : needsCheck ? "border-amber" : "border-border"
      }`}
    >
      <div className="mb-3 flex items-start justify-between gap-2">
        <p className="min-w-0 text-sm text-muted">
          <span className="sr-only">Written as: </span>“{line.rawText}”
        </p>
        <div className="flex shrink-0 items-center gap-1">
          {line.newProduct && (
            <span className="rounded-full bg-accent px-2 py-0.5 text-xs font-medium text-white">New</span>
          )}
          {differs && (
            <span className="rounded-full bg-amber/15 px-2 py-0.5 text-xs font-medium text-amber">
              Price differs
            </span>
          )}
          {needsCheck && (
            <span className="rounded-full bg-amber/15 px-2 py-0.5 text-xs font-medium text-amber">Check</span>
          )}
          <button
            type="button"
            onClick={onRemove}
            aria-label={`Remove line ${index + 1}`}
            className="flex h-9 w-9 items-center justify-center rounded-button text-muted hover:bg-background hover:text-red"
          >
            ✕
          </button>
        </div>
      </div>

      {needsCheck && (
        <p className="mb-3 text-xs text-amber">{line.checkReasons.map((r) => REASON_TEXT[r]).join(" · ")}</p>
      )}

      {line.newProduct ? (
        <div className="flex flex-col gap-3">
          <Field
            id={id("new-name")}
            label="New product name"
            value={line.newProduct.name}
            onChange={(e) => update({ newProduct: { ...line.newProduct!, name: e.target.value } })}
          />
          <div className="grid grid-cols-2 gap-3">
            <Select
              id={id("new-category")}
              label="Category"
              value={line.newProduct.category}
              onChange={(e) => update({ newProduct: { ...line.newProduct!, category: e.target.value } })}
            >
              {CATEGORIES.map((c) => (
                <option key={c}>{c}</option>
              ))}
            </Select>
            <Field
              id={id("new-unit")}
              label="Stock counted in"
              value={line.newProduct.base_unit}
              onChange={(e) => update({ newProduct: { ...line.newProduct!, base_unit: e.target.value } })}
            />
          </div>
          <button
            type="button"
            onClick={() => update({ newProduct: null })}
            className="self-start text-sm font-medium text-accent hover:underline"
          >
            Pick an existing product instead
          </button>
        </div>
      ) : (
        <ProductPicker
          value={line.product}
          invalid={problem === "Pick a product"}
          onPick={pickProduct}
          onAddNew={
            canCreate
              ? (name) => update({ product: null, newProduct: { name, category: "Others", base_unit: line.unit || "pc" } })
              : undefined
          }
        />
      )}

      {/* Qty + Unit row */}
      <div className="mt-3 grid grid-cols-2 gap-3">
        <Field
          id={id("qty")}
          label="Qty"
          inputMode="decimal"
          value={line.qty}
          onChange={(e) => update({ qty: e.target.value })}
        />
        <Field id={id("unit")} label="Unit" value={line.unit} onChange={(e) => update({ unit: e.target.value })} />
      </div>
      {/* Price + Total row */}
      <div className="mt-3 grid grid-cols-2 gap-3">
        <Field
          id={id("price")}
          label={`Price per ${line.unit || "unit"} (₱)`}
          inputMode="decimal"
          placeholder="Optional"
          value={line.price}
          onChange={(e) => update({ price: e.target.value })}
        />
        <div className="flex flex-col gap-1">
          <span className="text-sm font-medium text-text">Total</span>
          <span className="flex h-11 items-center font-medium text-text">
            {total === null ? <span className="text-muted">—</span> : formatPeso(total)}
          </span>
        </div>
      </div>

      {differs && line.expectedPrice !== null && (
        <p className="mt-2 text-xs text-amber">
          Usual price: {formatPeso(line.expectedPrice)} per {line.unit}
        </p>
      )}

      {problem && (
        <p role="alert" className="mt-2 text-sm text-red">
          {problem}
        </p>
      )}
    </li>
  );
}
