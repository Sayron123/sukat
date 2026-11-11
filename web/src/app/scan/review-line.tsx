"use client";

import { useState } from "react";

import { Icon } from "@/components/icons";
import { Badge, Field, Select } from "@/components/ui";
import { formatPeso } from "@/lib/format";
import { CATEGORIES } from "@/lib/types";

import {
  type EditLine,
  REASON_TEXT,
  editLine,
  lineProblem,
  lineTotal,
  priceDiffers,
} from "./lines";
import { guessCategory } from "./guess-category";
import { type PickedProduct, ProductPicker, useProductSearch } from "./product-picker";

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
  const [editing, setEditing] = useState(false);

  function pickProduct(p: PickedProduct) {
    const patch: Partial<EditLine> = { product: p };
    // Sale with no price yet: use the product's price when the unit is its base unit.
    // (For other units the server fills in the converted price when saving.)
    if (
      isSale &&
      (!line.price.trim() || line.priceFromProduct) &&
      p.price_centavos !== null &&
      line.unit === p.base_unit
    ) {
      patch.price = (p.price_centavos / 100).toFixed(2);
      patch.priceFromProduct = true;
    }
    update(patch);
  }
  const id = (name: string) => `line-${line.key}-${name}`;

  return (
    <li
      aria-label={`Line ${index + 1}`}
      className={`rounded-card border bg-background p-4 ${
        problem ? "border-red" : "border-border"
      } ${needsCheck ? "border-l-4 border-l-amber pl-[13px]" : ""}`}
    >
      <div className="flex items-start gap-2">
        {/* Badges move under the name when the name needs the room. */}
        <div className="flex min-w-0 flex-1 flex-wrap items-center gap-x-2 gap-y-1">
          <div className="min-w-[60%] flex-1">
            {line.newProduct ? (
              editing ? (
                <NameEditor
                  id={id("new-name")}
                  name={line.newProduct.name}
                  onName={(name) => update({ newProduct: { ...line.newProduct!, name } })}
                  onUse={(p) => {
                    setEditing(false);
                    update({ product: p, newProduct: null });
                  }}
                  onDone={() => setEditing(false)}
                />
              ) : (
                <b className={`block py-1.5 text-base ${line.newProduct.name.trim() ? "text-text" : "text-red"}`}>
                  {line.newProduct.name.trim() || "No name yet"}
                </b>
              )
            ) : (
              <ProductPicker
                value={line.product}
                invalid={problem === "Pick a product"}
                onPick={pickProduct}
                onAddNew={
                  canCreate
                    ? (name) =>
                        update({
                          product: null,
                          newProduct: {
                            name,
                            category: guessCategory(name),
                            base_unit: line.unit,
                          },
                        })
                    : undefined
                }
              />
            )}
          </div>
          {line.newProduct && !editing && <Badge>New</Badge>}
          {differs && <Badge tone="amber">Price differs</Badge>}
          {needsCheck && <Badge tone="amber">Check</Badge>}
        </div>
        <button
          type="button"
          onClick={onRemove}
          aria-label={`Remove line ${index + 1}`}
          className="-mr-2 grid h-9 w-9 shrink-0 place-items-center rounded-button text-subtle hover:bg-surface hover:text-red"
        >
          <Icon name="close" size={18} />
        </button>
      </div>

      <p className="mt-0.5 mb-3 text-[13px] text-subtle">
        Written as “{line.rawText}”
        {needsCheck && (
          <span className="text-amber-text">
            {" "}
            · {line.checkReasons.map((r) => REASON_TEXT[r]).join(" · ")}
          </span>
        )}
      </p>

      {line.newProduct && (
        <div className="mb-3 grid grid-cols-2 gap-2">
          <Select
            id={id("new-category")}
            label="Category"
            value={line.newProduct.category}
            onChange={(e) =>
              update({
                newProduct: { ...line.newProduct!, category: e.target.value },
              })
            }
          >
            {CATEGORIES.map((c) => (
              <option key={c}>{c}</option>
            ))}
          </Select>
          <Field
            id={id("new-unit")}
            label="Stock counted in"
            value={line.newProduct.base_unit}
            onChange={(e) =>
              update({
                newProduct: { ...line.newProduct!, base_unit: e.target.value },
              })
            }
          />
          {!editing && (
            <button
              type="button"
              onClick={() => setEditing(true)}
              className="col-span-2 flex min-h-10 items-center gap-1.5 self-start text-[13px] font-semibold text-text"
            >
              <Icon name="edit" size={16} />
              Edit name
            </button>
          )}
        </div>
      )}

      {/* Qty / Unit / Price / Total, as in the design */}
      <div className="grid grid-cols-[48px_58px_76px_1fr] items-end gap-[7px]">
        <Field
          id={id("qty")}
          label="Qty"
          compact
          inputMode="decimal"
          invalid={problem === "Enter a quantity"}
          value={line.qty}
          onChange={(e) => update({ qty: e.target.value })}
        />
        <Field
          id={id("unit")}
          label="Unit"
          compact
          invalid={problem === "Enter a unit"}
          value={line.unit}
          onChange={(e) => update({ unit: e.target.value })}
        />
        <Field
          id={id("price")}
          label="Price"
          compact
          inputMode="decimal"
          placeholder="—"
          invalid={problem?.startsWith("Price") ?? false}
          value={line.price}
          onChange={(e) => update({ price: e.target.value })}
        />
        <div className="min-w-0 pb-[9px] text-right">
          <span className="mb-1.5 block text-[13px] text-subtle">Total</span>
          <b className="text-[13px] whitespace-nowrap text-text">
            {total === null ? (
              <span className="text-subtle">—</span>
            ) : (
              formatPeso(total)
            )}
          </b>
        </div>
      </div>

      {differs && line.expectedPrice !== null && (
        <p className="mt-2 text-[13px] text-amber-text">
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

function NameEditor({
  id,
  name,
  onName,
  onUse,
  onDone,
}: {
  id: string;
  name: string;
  onName: (name: string) => void;
  onUse: (p: PickedProduct) => void;
  onDone: () => void;
}) {
  const matches = useProductSearch(name, name.trim().length >= 2).slice(0, 3);
  return (
    <div>
      <div className="flex gap-2">
        <input
          id={id}
          aria-label="Product name"
          value={name}
          placeholder="Product name"
          autoFocus
          maxLength={160}
          onChange={(e) => onName(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") {
              e.preventDefault();
              onDone();
            }
          }}
          className="h-10 w-full min-w-0 flex-1 rounded-button border border-text bg-background px-3 text-base font-bold text-text outline-none"
        />
        <button
          type="button"
          onClick={onDone}
          className="h-10 shrink-0 rounded-button bg-text px-3 text-sm font-bold text-inverse"
        >
          Done
        </button>
      </div>
      {matches.length > 0 && (
        <div className="mt-2">
          <p className="text-[13px] text-subtle">Already in your products? Tap to use it.</p>
          <ul className="mt-1.5 flex flex-col gap-1.5">
            {matches.map((p) => (
              <li key={p.id}>
                <button
                  type="button"
                  onClick={() => onUse(p)}
                  className="flex min-h-11 w-full items-center justify-between gap-2 rounded-button border border-line px-3 text-left hover:bg-surface"
                >
                  <span className="min-w-0 text-sm font-semibold text-text">{p.name}</span>
                  <span className="shrink-0 text-xs text-muted">{p.base_unit}</span>
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
