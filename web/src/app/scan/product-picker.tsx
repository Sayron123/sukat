"use client";

import { useEffect, useId, useState } from "react";

import { Icon } from "@/components/icons";
import { api } from "@/lib/api-client";
import type { ProductPage } from "@/lib/types";

export type PickedProduct = {
  id: string;
  name: string;
  base_unit: string;
  price_centavos: number | null;
};

/**
 * Search box that picks one of the store's products. Shows up to 6 matches by name or
 * alias. `onAddNew` (optional) offers "Add as new product" with the typed text.
 */
export function useProductSearch(text: string, enabled: boolean): PickedProduct[] {
  const [results, setResults] = useState<PickedProduct[]>([]);

  useEffect(() => {
    if (!enabled) return;
    let stale = false;
    const t = setTimeout(() => {
      const q = text.trim();
      api<ProductPage>(`products?${new URLSearchParams(q ? { q } : {})}`)
        .then((page) => {
          if (!stale)
            setResults(
              page.items.slice(0, 6).map((p) => ({
                id: p.id,
                name: p.name,
                base_unit: p.base_unit,
                price_centavos: p.price_centavos,
              })),
            );
        })
        .catch(() => {
          if (!stale) setResults([]);
        });
    }, 250);
    return () => {
      stale = true;
      clearTimeout(t);
    };
  }, [text, enabled]);

  return results;
}

export function ProductPicker({
  value,
  onPick,
  onAddNew,
  invalid,
  label = "Product",
}: {
  value: PickedProduct | null;
  onPick: (p: PickedProduct) => void;
  onAddNew?: (name: string) => void;
  invalid?: boolean;
  label?: string;
}) {
  const listId = useId();
  const [text, setText] = useState(value?.name ?? "");
  const [open, setOpen] = useState(false);
  const results = useProductSearch(text, open);

  return (
    <div className="relative">
      <input
        role="combobox"
        aria-expanded={open}
        aria-controls={listId}
        aria-label={label}
        aria-invalid={invalid || undefined}
        value={text}
        placeholder="Pick a product"
        onFocus={() => setOpen(true)}
        // Delay so a tap on a result registers before the list closes.
        onBlur={() => setTimeout(() => setOpen(false), 150)}
        onChange={(e) => {
          setText(e.target.value);
          setOpen(true);
        }}
        // Looks like the line's bold title; underlined while typing or when missing.
        className={`h-9 w-full min-w-0 border-b bg-transparent text-base font-bold text-text outline-none placeholder:font-semibold focus:border-text ${
          invalid ? "border-red placeholder:text-red" : "border-transparent placeholder:text-subtle"
        }`}
      />
      {open && (results.length > 0 || (onAddNew && text.trim())) && (
        <ul
          id={listId}
          role="listbox"
          className="absolute inset-x-0 top-10 z-20 max-h-72 overflow-y-auto rounded-button border border-border bg-background shadow-lg"
        >
          {results.map((p) => (
            <li key={p.id} role="option" aria-selected={value?.id === p.id}>
              <button
                type="button"
                onMouseDown={(e) => e.preventDefault()}
                onClick={() => {
                  onPick({ id: p.id, name: p.name, base_unit: p.base_unit, price_centavos: p.price_centavos });
                  setText(p.name);
                  setOpen(false);
                }}
                className="flex min-h-11 w-full items-center justify-between gap-2 px-3 py-2 text-left hover:bg-surface"
              >
                <span className="text-text">{p.name}</span>
                <span className="shrink-0 text-xs text-muted">{p.base_unit}</span>
              </button>
            </li>
          ))}
          {onAddNew && text.trim() && (
            <li role="option" aria-selected={false}>
              <button
                type="button"
                onMouseDown={(e) => e.preventDefault()}
                onClick={() => {
                  onAddNew(text.trim());
                  setOpen(false);
                }}
                className="flex min-h-11 w-full items-center gap-1.5 px-3 py-2 text-left font-semibold text-text hover:bg-surface"
              >
                <Icon name="plus" size={18} />
                Add &quot;{text.trim()}&quot; as new product
              </button>
            </li>
          )}
        </ul>
      )}
    </div>
  );
}
