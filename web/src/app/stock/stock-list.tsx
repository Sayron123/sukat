"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { Card, Chip } from "@/components/ui";
import { ApiError, api } from "@/lib/api-client";
import { formatPeso, formatQty } from "@/lib/format";
import { CATEGORIES, canEditProducts, type Category, type Me, type ProductPage } from "@/lib/types";

const linkButton =
  "flex h-11 items-center justify-center rounded-button px-4 text-sm font-medium";

export function StockList() {
  const [me, setMe] = useState<Me | null>(null);
  const [query, setQuery] = useState("");
  const [debounced, setDebounced] = useState("");
  const [category, setCategory] = useState<Category | null>(null);
  const [page, setPage] = useState(1);
  const [data, setData] = useState<ProductPage | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api<Me>("auth/me").then(setMe, () => {});
  }, []);

  // Wait until typing pauses (300 ms) before searching, so we don't call the API per key.
  useEffect(() => {
    const t = setTimeout(() => setDebounced(query.trim()), 300);
    return () => clearTimeout(t);
  }, [query]);

  useEffect(() => {
    const params = new URLSearchParams({ page: String(page) });
    if (debounced) params.set("q", debounced);
    if (category) params.set("category", category);
    let stale = false; // ignore answers to older searches that arrive late
    api<ProductPage>(`products?${params}`)
      .then((res) => {
        if (stale) return;
        setData(res);
        setError(null);
      })
      .catch((e: unknown) => {
        if (!stale) setError(e instanceof ApiError ? e.message : "Could not load products");
      });
    return () => {
      stale = true;
    };
  }, [debounced, category, page]);

  const canEdit = canEditProducts(me?.role);
  const filtering = debounced !== "" || category !== null;

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center justify-between gap-2">
        <h1 className="text-2xl font-semibold text-text">Stock</h1>
        {canEdit && (
          <div className="flex gap-2">
            <Link
              href="/stock/import"
              className={`${linkButton} border border-border bg-background text-text hover:bg-surface`}
            >
              Import
            </Link>
            <Link
              href="/stock/new"
              className={`${linkButton} bg-accent text-white hover:bg-accent-pressed`}
            >
              + Add
            </Link>
          </div>
        )}
      </div>

      <input
        type="search"
        value={query}
        onChange={(e) => {
          setQuery(e.target.value);
          setPage(1);
        }}
        placeholder="Search name or alias (e.g. sem, bakal 10mm)"
        aria-label="Search products"
        className="h-11 rounded-button border border-border bg-background px-3 text-text outline-none focus:border-accent focus:ring-2 focus:ring-accent/30"
      />

      <div className="-mx-4 flex gap-2 overflow-x-auto px-4 pb-1" role="group" aria-label="Category">
        <Chip selected={category === null} onClick={() => (setCategory(null), setPage(1))}>
          All
        </Chip>
        {CATEGORIES.map((c) => (
          <Chip key={c} selected={category === c} onClick={() => (setCategory(c), setPage(1))}>
            {c}
          </Chip>
        ))}
      </div>

      {error && (
        <p role="alert" className="text-sm text-red">
          {error}
        </p>
      )}

      {!data ? (
        <p className="text-muted">Loading…</p>
      ) : data.items.length === 0 ? (
        <Card className="text-center">
          {filtering ? (
            <p className="text-muted">No products match.</p>
          ) : (
            <>
              <p className="font-medium text-text">No products yet</p>
              {canEdit && (
                <Link
                  href="/stock/import"
                  className={`${linkButton} mx-auto mt-4 w-fit bg-accent text-white hover:bg-accent-pressed`}
                >
                  Import starter items
                </Link>
              )}
            </>
          )}
        </Card>
      ) : (
        <>
          <p className="text-sm text-muted">
            {data.total} product{data.total === 1 ? "" : "s"}
          </p>
          <Card padded={false}>
            <ul className="divide-y divide-border">
              {data.items.map((p) => {
                const row = (
                  <div className="flex items-start justify-between gap-3 px-4 py-3">
                    <div className="min-w-0">
                      <p className="font-medium text-text">{p.name}</p>
                      <p className="text-sm text-muted">
                        {p.category} · {formatPeso(p.price_centavos)}
                        {p.price_centavos !== null && ` / ${p.base_unit}`}
                      </p>
                    </div>
                    <div className="flex shrink-0 flex-col items-end gap-1">
                      <span className="font-medium text-text">
                        {formatQty(p.stock_qty)} {p.base_unit}
                      </span>
                      {p.is_low_stock && (
                        <span className="rounded-full bg-amber/15 px-2 py-0.5 text-xs font-medium text-amber">
                          Low stock
                        </span>
                      )}
                    </div>
                  </div>
                );
                return (
                  <li key={p.id}>
                    {canEdit ? (
                      <Link href={`/stock/${p.id}`} className="block hover:bg-background">
                        {row}
                      </Link>
                    ) : (
                      row
                    )}
                  </li>
                );
              })}
            </ul>
          </Card>
          {data.pages > 1 && (
            <div className="flex items-center justify-between">
              <button
                type="button"
                disabled={page <= 1}
                onClick={() => setPage(page - 1)}
                className="h-11 rounded-button border border-border px-4 text-sm font-medium text-text disabled:opacity-40"
              >
                Previous
              </button>
              <span className="text-sm text-muted">
                Page {data.page} of {data.pages}
              </span>
              <button
                type="button"
                disabled={page >= data.pages}
                onClick={() => setPage(page + 1)}
                className="h-11 rounded-button border border-border px-4 text-sm font-medium text-text disabled:opacity-40"
              >
                Next
              </button>
            </div>
          )}
        </>
      )}
    </div>
  );
}
