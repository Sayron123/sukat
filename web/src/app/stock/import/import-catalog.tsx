"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";

import { Button, Card } from "@/components/ui";
import { ApiError, api } from "@/lib/api-client";
import { CATEGORIES, type CatalogItem, type ImportResult } from "@/lib/types";

/** Pick starter items by category and copy them into this store. */
export function ImportCatalog() {
  const [items, setItems] = useState<CatalogItem[] | null>(null);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [filter, setFilter] = useState("");
  const [result, setResult] = useState<ImportResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    api<CatalogItem[]>("catalog").then(setItems, (e: unknown) =>
      setError(e instanceof ApiError ? e.message : "Could not load the catalog"),
    );
  }, []);

  const groups = useMemo(() => {
    const term = filter.trim().toLowerCase();
    const visible = (items ?? []).filter(
      (i) => !term || i.name.toLowerCase().includes(term) || i.aliases.some((a) => a.includes(term)),
    );
    return CATEGORIES.map((c) => ({ category: c, items: visible.filter((i) => i.category === c) })).filter(
      (g) => g.items.length > 0,
    );
  }, [items, filter]);

  function toggle(keys: string[], on: boolean) {
    const next = new Set(selected);
    for (const k of keys) {
      if (on) next.add(k);
      else next.delete(k);
    }
    setSelected(next);
  }

  async function runImport() {
    setSaving(true);
    setError(null);
    try {
      const res = await api<ImportResult>("products/import", {
        method: "POST",
        body: JSON.stringify({ keys: [...selected] }),
      });
      setResult(res);
      setSelected(new Set());
      setItems(await api<CatalogItem[]>("catalog")); // refresh "Added" marks
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Import failed");
    } finally {
      setSaving(false);
    }
  }

  if (error && !items) return <p className="text-red">{error}</p>;
  if (!items) return <p className="text-muted">Loading…</p>;

  return (
    <div className="flex flex-col gap-4 pb-24">
      <div>
        <div className="flex items-center justify-between">
          <h1 className="text-2xl font-semibold text-text">Import starter items</h1>
          <Link href="/stock" className="text-sm font-medium text-accent hover:underline">
            Done
          </Link>
        </div>
        <p className="mt-1 text-sm text-muted">
          Pick what your store sells. You can set prices and edit names after.
        </p>
      </div>

      {result && (
        <Card role="status" className="text-sm text-text">
          Added {result.created} product{result.created === 1 ? "" : "s"}.
          {result.skipped.length > 0 && ` ${result.skipped.length} already in your store.`}
          {result.dropped_aliases.length > 0 &&
            ` ${result.dropped_aliases.length} other name(s) were left off because another product uses them.`}
        </Card>
      )}

      <input
        type="search"
        value={filter}
        onChange={(e) => setFilter(e.target.value)}
        placeholder="Filter items"
        aria-label="Filter items"
        className="h-11 rounded-button border border-border bg-background px-3 text-text outline-none focus:border-accent focus:ring-2 focus:ring-accent/30"
      />

      {groups.map(({ category, items: group }) => {
        const selectable = group.filter((i) => !i.already_in_store).map((i) => i.key);
        const allOn = selectable.length > 0 && selectable.every((k) => selected.has(k));
        return (
          <Card key={category} padded={false}>
            <div className="flex items-center justify-between border-b border-border px-4 py-3">
              <h2 className="font-semibold text-text">{category}</h2>
              {selectable.length > 0 && (
                <button
                  type="button"
                  onClick={() => toggle(selectable, !allOn)}
                  className="text-sm font-medium text-accent hover:underline"
                >
                  {allOn ? "Clear" : "Select all"}
                </button>
              )}
            </div>
            <ul className="divide-y divide-border">
              {group.map((item) => (
                <li key={item.key}>
                  <label
                    className={`flex min-h-11 items-center gap-3 px-4 py-2 ${item.already_in_store ? "opacity-60" : "cursor-pointer"}`}
                  >
                    <input
                      type="checkbox"
                      className="h-5 w-5 shrink-0 accent-accent"
                      checked={item.already_in_store || selected.has(item.key)}
                      disabled={item.already_in_store}
                      onChange={(e) => toggle([item.key], e.target.checked)}
                    />
                    <span className="min-w-0 flex-1">
                      <span className="block text-text">{item.name}</span>
                      <span className="block truncate text-xs text-muted">
                        {item.base_unit} · {item.aliases.slice(0, 3).join(", ")}
                      </span>
                    </span>
                    {item.already_in_store && <span className="text-xs text-green">Added</span>}
                  </label>
                </li>
              ))}
            </ul>
          </Card>
        );
      })}

      {error && (
        <p role="alert" className="text-sm text-red">
          {error}
        </p>
      )}

      <div className="fixed inset-x-0 bottom-0 border-t border-border bg-background p-4">
        <div className="mx-auto max-w-2xl">
          <Button type="button" className="w-full" disabled={selected.size === 0 || saving} onClick={runImport}>
            {saving ? "Importing…" : `Import ${selected.size} item${selected.size === 1 ? "" : "s"}`}
          </Button>
        </div>
      </div>
    </div>
  );
}
