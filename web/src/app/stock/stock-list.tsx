"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { ActionDock } from "@/components/action-dock";
import { Icon } from "@/components/icons";
import { PageHeader, headerIconClass } from "@/components/page-header";
import { ScanButton } from "@/components/scan-button";
import { Badge, Card, Chip, Pager, SearchBox, buttonClass } from "@/components/ui";
import { ApiError, api } from "@/lib/api-client";
import { formatPeso, formatQty } from "@/lib/format";
import { CATEGORIES, canEditProducts, type Category, type Me, type ProductPage } from "@/lib/types";

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
    <>
      <PageHeader
        eyebrow={data ? `${data.total} product${data.total === 1 ? "" : "s"}` : " "}
        title="Stock"
        action={
          canEdit && (
            <Link href="/stock/new" aria-label="Add product" className={headerIconClass}>
              <Icon name="plus" size={24} />
            </Link>
          )
        }
      />

      <SearchBox
        value={query}
        onChange={(e) => {
          setQuery(e.target.value);
          setPage(1);
        }}
        maxLength={80}
        placeholder="Search products"
        aria-label="Search products (name or other name, e.g. sem, bakal 10mm)"
      />

      <div
        className="-mx-5 mt-4 mb-[22px] flex gap-2 overflow-x-auto px-5 [scrollbar-width:none]"
        role="group"
        aria-label="Category"
      >
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
        <p role="alert" className="mb-3 text-sm text-red">
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
              <p className="font-bold text-text">No products yet</p>
              {canEdit && (
                <Link href="/stock/import" className={`${buttonClass()} mt-4`}>
                  Import starter items
                </Link>
              )}
            </>
          )}
        </Card>
      ) : (
        <div className="flex flex-col gap-3">
          <ul className="flex flex-col gap-3">
            {data.items.map((p) => {
              const row = (
                <Card className="flex min-h-[88px] items-center gap-2">
                  <div className="min-w-0 flex-1">
                    <p className="flex items-center gap-[7px]">
                      <b className="min-w-0 text-base text-text">{p.name}</b>
                      {p.is_low_stock && <Badge tone="red">Low</Badge>}
                    </p>
                    <small className="mt-[5px] block text-sm text-muted">
                      {p.category} · {formatPeso(p.price_centavos)}
                      {p.price_centavos !== null && `/${p.base_unit}`}
                    </small>
                  </div>
                  <div className="min-w-[62px] shrink-0 text-right">
                    <strong className="block text-2xl leading-none text-text">{formatQty(p.stock_qty)}</strong>
                    <span className="text-[13px] text-muted">{p.base_unit}</span>
                  </div>
                </Card>
              );
              return (
                <li key={p.id}>
                  <Link href={`/stock/${p.id}`} className="block rounded-card hover:bg-surface">
                    {row}
                  </Link>
                </li>
              );
            })}
          </ul>
          <Pager page={data.page} pages={data.pages} onPage={setPage} />
        </div>
      )}

      <ActionDock>
        <ScanButton href="/scan" />
      </ActionDock>
    </>
  );
}
