"use client";

import { useEffect, useMemo, useState } from "react";

import { ActionDock } from "@/components/action-dock";
import { PageHeader } from "@/components/page-header";
import { Badge, Button, Loading, Notice, SearchBox } from "@/components/ui";
import { ApiError, api } from "@/lib/api-client";
import { CATEGORIES, type CatalogItem, type ImportResult } from "@/lib/types";

function plural(n: number, word: string): string {
  return `${n} ${word}${n === 1 ? "" : "s"}`;
}

function importTitle(result: ImportResult): string {
  if (result.created > 0) return `Added ${plural(result.created, "product")}`;
  if (result.restored > 0) return `Brought back ${plural(result.restored, "product")}`;
  return "Added 0 products";
}

function importNotes(result: ImportResult): string {
  const notes = [
    result.created > 0 && result.restored > 0 && `${plural(result.restored, "archived product")} brought back.`,
    result.skipped.length > 0 && `${result.skipped.length} already in your store.`,
    result.dropped_aliases.length > 0 &&
      `${result.dropped_aliases.length} other name(s) were left off because another product uses them.`,
  ].filter(Boolean);
  return notes.length > 0 ? notes.join(" ") : "They are now in your stock list.";
}

/** Pick starter items by category and copy them into this store. */
export function ImportCatalog() {
  const [items, setItems] = useState<CatalogItem[] | null>(null);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [filter, setFilter] = useState("");
  const [result, setResult] = useState<ImportResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    api<CatalogItem[]>("products/catalog").then(setItems, (e: unknown) =>
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
      setItems(await api<CatalogItem[]>("products/catalog")); // refresh "Added" marks
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Import failed");
    } finally {
      setSaving(false);
    }
  }

  const header = <PageHeader eyebrow="Starter items" title="Import products" back="/stock" />;
  if (error && !items)
    return (
      <>
        {header}
        <p className="text-red">{error}</p>
      </>
    );
  if (!items)
    return (
      <>
        {header}
        <Loading />
      </>
    );

  return (
    <>
      {header}
      <p className="-mt-2 mb-5 text-sm text-muted">
        Pick what your store sells. You can set prices and edit names after.
      </p>

      {result && (
        <Notice role="status" icon="check" title={importTitle(result)} className="mb-5">
          {importNotes(result)}
        </Notice>
      )}

      <SearchBox
        value={filter}
        onChange={(e) => setFilter(e.target.value)}
        placeholder="Filter items"
        aria-label="Filter items"
      />

      {groups.map(({ category, items: group }) => {
        const selectable = group.filter((i) => !i.already_in_store).map((i) => i.key);
        const allOn = selectable.length > 0 && selectable.every((k) => selected.has(k));
        return (
          <section key={category} className="mt-6">
            <div className="mb-2 flex items-center justify-between">
              <h2 className="text-[13px] font-bold text-subtle uppercase">{category}</h2>
              {selectable.length > 0 && (
                <button
                  type="button"
                  onClick={() => toggle(selectable, !allOn)}
                  className="min-h-10 text-[13px] font-semibold text-muted underline"
                >
                  {allOn ? "Clear" : "Select all"}
                </button>
              )}
            </div>
            <ul className="divide-y divide-border rounded-card border border-border px-4">
              {group.map((item) => (
                <li key={item.key}>
                  <label
                    className={`flex min-h-16 items-center gap-3 py-2 ${item.already_in_store ? "opacity-60" : "cursor-pointer"}`}
                  >
                    <input
                      type="checkbox"
                      className="h-5 w-5 shrink-0 accent-text"
                      checked={item.already_in_store || selected.has(item.key)}
                      disabled={item.already_in_store}
                      onChange={(e) => toggle([item.key], e.target.checked)}
                    />
                    <span className="min-w-0 flex-1">
                      <b className="block text-[15px] text-text">{item.name}</b>
                      <small className="mt-0.5 block truncate text-[13px] text-muted">
                        {item.base_unit} · {item.aliases.slice(0, 3).join(", ")}
                      </small>
                    </span>
                    {item.already_in_store && <Badge tone="green">Added</Badge>}
                  {item.archived_in_store && <Badge>Archived</Badge>}
                  </label>
                </li>
              ))}
            </ul>
          </section>
        );
      })}

      <ActionDock>
        {error && (
          <p role="alert" className="text-sm text-red">
            {error}
          </p>
        )}
        <Button type="button" size="lg" disabled={selected.size === 0 || saving} onClick={runImport}>
          {saving ? "Importing…" : `Import ${selected.size} item${selected.size === 1 ? "" : "s"}`}
        </Button>
      </ActionDock>
    </>
  );
}
