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
  needsApproval,
  priceDiffers,
} from "./lines";
import { guessCategory } from "./guess-category";
import { type PickedProduct, ProductPicker, nameInputClass, useProductSearch } from "./product-picker";

/**
 * One editable line on the review screen.
 * - Red edge + "Please double check this line": the AI was unsure, until the user taps Approve.
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
  const needsCheck = needsApproval(line);
  const differs = isSale && priceDiffers(line);
  const problem = showErrors ? lineProblem(line) : null;
  const total = lineTotal(line);
  const update = (patch: Partial<EditLine>) => onChange(editLine(line, patch));

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
      data-needs-check={needsCheck || undefined}
      className={`scroll-mt-28 rounded-card border bg-background p-4 ${
        problem ? "border-red" : needsCheck ? "border-red-edge" : "border-border"
      } ${needsCheck ? "border-l-4 border-l-red pl-[13px]" : ""}`}
    >
      <div className="flex items-start gap-2">
        {/* Badges move under the name when the name needs the room. */}
        <div className="flex min-w-0 flex-1 flex-wrap items-center gap-x-2 gap-y-1">
          <div className="min-w-[60%] flex-1">
            {line.newProduct ? (
              <NewNameField
                id={id("new-name")}
                name={line.newProduct.name}
                invalid={problem === "Enter the new product's name"}
                onName={(name) => update({ newProduct: { ...line.newProduct!, name } })}
                onUse={(p) => update({ product: p, newProduct: null })}
              />
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
          {line.newProduct && <Badge>New</Badge>}
          {differs && <Badge tone="amber">Price differs</Badge>}
          {line.approved && <Badge tone="green">Approved</Badge>}
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

      <p className="mt-0.5 mb-3 text-[13px] text-subtle">Written as “{line.rawText}”</p>

      {needsCheck && (
        <div className="mb-3 flex gap-2.5 rounded-button border border-red-edge bg-red-soft p-3">
          <Icon name="alert" size={20} className="mt-px text-red" />
          <div className="min-w-0 flex-1">
            <p className="text-sm font-bold text-red">Please double check this line</p>
            <p className="mt-0.5 text-[13px] leading-snug text-text">
              {line.checkReasons.map((r) => REASON_TEXT[r]).join(" · ")}
            </p>
            <button
              type="button"
              onClick={() => update({ approved: true })}
              className="mt-2.5 flex h-10 items-center gap-1.5 rounded-button border border-red-edge bg-background px-4 text-sm font-bold text-text hover:bg-surface"
            >
              <Icon name="check" size={18} />
              Approve
            </button>
          </div>
        </div>
      )}

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

function NewNameField({
  id,
  name,
  invalid,
  onName,
  onUse,
}: {
  id: string;
  name: string;
  invalid: boolean;
  onName: (name: string) => void;
  onUse: (p: PickedProduct) => void;
}) {
  const [typing, setTyping] = useState(false);
  const matches = useProductSearch(name, typing && name.trim().length >= 2).slice(0, 3);
  return (
    <div className="relative">
      <input
        id={id}
        aria-label="Product name"
        aria-invalid={invalid || undefined}
        value={name}
        placeholder="Product name"
        maxLength={160}
        onChange={(e) => {
          onName(e.target.value);
          setTyping(true);
        }}
        onBlur={() => setTimeout(() => setTyping(false), 150)}
        className={nameInputClass(invalid)}
      />
      {typing && matches.length > 0 && (
        <div className="absolute inset-x-0 top-11 z-20 rounded-button border border-border bg-surface py-1 shadow-lg">
          <p className="px-3 pt-1 pb-1.5 text-[13px] text-subtle">Already in your products? Tap to use it.</p>
          <ul>
            {matches.map((p) => (
              <li key={p.id}>
                <button
                  type="button"
                  onMouseDown={(e) => e.preventDefault()}
                  onClick={() => {
                    setTyping(false);
                    onUse(p);
                  }}
                  className="flex min-h-11 w-full items-center justify-between gap-2 px-3 py-2 text-left hover:bg-surface"
                >
                  <span className="text-text">{p.name}</span>
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
