"use client";

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
              <input
                id={id("new-name")}
                aria-label="New product name"
                value={line.newProduct.name}
                placeholder="New product name"
                onChange={(e) =>
                  update({
                    newProduct: { ...line.newProduct!, name: e.target.value },
                  })
                }
                className="h-9 w-full min-w-0 border-b border-transparent bg-transparent text-base font-bold text-text outline-none focus:border-text"
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
          <span className="text-[#b45309]">
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
          <button
            type="button"
            onClick={() => update({ newProduct: null })}
            className="col-span-2 min-h-10 self-start text-left text-[13px] text-muted underline"
          >
            Pick an existing product instead
          </button>
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
        <p className="mt-2 text-[13px] text-[#b45309]">
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
