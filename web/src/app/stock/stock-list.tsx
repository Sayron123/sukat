"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { ActionDock } from "@/components/action-dock";
import { ConfirmDialog } from "@/components/confirm-dialog";
import { Icon } from "@/components/icons";
import { MascotMessage } from "@/components/mascot";
import { PageHeader, headerIconClass } from "@/components/page-header";
import { ScanButton } from "@/components/scan-button";
import { Badge, Button, Card, Chip, Notice, Pager, SearchBox, buttonClass } from "@/components/ui";
import { ApiError, api } from "@/lib/api-client";
import { formatPeso, formatQty } from "@/lib/format";
import {
  CATEGORIES,
  canEditProducts,
  type Category,
  type Me,
  type Product,
  type ProductDeleteResult,
  type ProductPage,
} from "@/lib/types";
import { useLongPress } from "@/lib/use-long-press";

export function StockList() {
  const [me, setMe] = useState<Me | null>(null);
  const [query, setQuery] = useState("");
  const [debounced, setDebounced] = useState("");
  const [category, setCategory] = useState<Category | null>(null);
  const [page, setPage] = useState(1);
  const [data, setData] = useState<ProductPage | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<Set<string> | null>(null);
  const [confirming, setConfirming] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [result, setResult] = useState<ProductDeleteResult | null>(null);
  const [reload, setReload] = useState(0);
  const press = useLongPress();

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
  }, [debounced, category, page, reload]);

  const canEdit = canEditProducts(me?.role);
  const canDelete = me?.role === "manager";
  const filtering = debounced !== "" || category !== null;
  const allSelected = selected !== null && data !== null && data.total > 0 && selected.size >= data.total;

  function toggle(id: string) {
    if (press.isHolding()) return;
    setSelected((current) => {
      const next = new Set(current);
      if (!next.delete(id)) next.add(id);
      return next;
    });
  }

  async function toggleAll() {
    if (allSelected) {
      setSelected(new Set());
      return;
    }
    const params = new URLSearchParams();
    if (debounced) params.set("q", debounced);
    if (category) params.set("category", category);
    try {
      setSelected(new Set(await api<string[]>(`products/ids?${params}`)));
      setError(null);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not select all products");
    }
  }

  async function deleteSelected() {
    if (!selected) return;
    setDeleting(true);
    try {
      const body = JSON.stringify({ ids: [...selected] });
      setResult(await api<ProductDeleteResult>("products/bulk-delete", { method: "POST", body }));
      setSelected(null);
      setPage(1);
      setReload((n) => n + 1);
      setError(null);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not delete the products");
    } finally {
      setDeleting(false);
      setConfirming(false);
    }
  }

  return (
    <>
      {selected ? (
        <PageHeader
          eyebrow="Select items"
          title={`${selected.size} selected`}
          onBack={() => setSelected(null)}
          action={
            <button type="button" onClick={toggleAll} className="min-h-11 shrink-0 px-1 text-sm font-bold text-text">
              {allSelected ? "Deselect all" : "Select all"}
            </button>
          }
        />
      ) : (
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
      )}

      <div inert={selected !== null} className={selected ? "opacity-50" : undefined}>
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
      </div>

      {result && <DeleteResult result={result} />}

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
            <MascotMessage emote="searching" title="No products match">
              Try another name or category.
            </MascotMessage>
          ) : (
            <>
              <MascotMessage emote="empty" title="No products yet" />
              {canEdit && (
                <Link href="/stock/import" className={`${buttonClass()} mt-2`}>
                  Import starter items
                </Link>
              )}
            </>
          )}
        </Card>
      ) : (
        <div className="flex flex-col gap-3">
          <ul className="flex flex-col gap-3">
            {data.items.map((p) => (
              <StockRow
                key={p.id}
                product={p}
                press={canDelete ? press.handlers(() => setSelected(new Set([p.id]))) : undefined}
                selected={selected ? selected.has(p.id) : null}
                onToggle={() => toggle(p.id)}
              />
            ))}
          </ul>
          <Pager page={data.page} pages={data.pages} onPage={setPage} />
        </div>
      )}

      <ActionDock>
        {selected ? (
          <Button
            type="button"
            variant="danger"
            size="lg"
            icon="trash"
            disabled={selected.size === 0}
            onClick={() => setConfirming(true)}
          >
            {selected.size > 0 ? `Delete (${selected.size})` : "Delete"}
          </Button>
        ) : (
          <ScanButton />
        )}
      </ActionDock>

      <ConfirmDialog
        open={confirming}
        title={`Delete ${selected?.size ?? 0} ${selected?.size === 1 ? "item" : "items"}?`}
        confirmLabel="Delete"
        danger
        busy={deleting}
        onConfirm={deleteSelected}
        onCancel={() => setConfirming(false)}
      >
        This can&apos;t be undone. Items with sales or stock history will be kept.
      </ConfirmDialog>
    </>
  );
}

function StockRow({
  product: p,
  press,
  selected,
  onToggle,
}: {
  product: Product;
  press?: ReturnType<ReturnType<typeof useLongPress>["handlers"]>;
  selected: boolean | null;
  onToggle: () => void;
}) {
  const card = (
    <Card className="flex min-h-[88px] items-center gap-2">
      {selected !== null && (
        <span
          className={`mr-1 grid h-6 w-6 shrink-0 place-items-center rounded-full border ${
            selected ? "border-accent bg-accent text-white" : "border-line"
          }`}
        >
          {selected && <Icon name="check" size={14} />}
        </span>
      )}
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

  if (selected !== null) {
    return (
      <li>
        <button
          type="button"
          aria-pressed={selected}
          onClick={onToggle}
          className={`block w-full rounded-card text-left ${selected ? "ring-2 ring-text" : ""}`}
        >
          {card}
        </button>
      </li>
    );
  }
  return (
    <li>
      <Link
        href={`/stock/${p.id}`}
        draggable={false}
        className={`block rounded-card hover:bg-surface ${press ? "select-none [-webkit-touch-callout:none]" : ""}`}
        {...press}
      >
        {card}
      </Link>
    </li>
  );
}

function DeleteResult({ result }: { result: ProductDeleteResult }) {
  const shown = result.kept.slice(0, 3).join(", ");
  const more = result.kept.length - 3;
  return (
    <Notice
      icon="check"
      title={`Deleted ${result.deleted} ${result.deleted === 1 ? "item" : "items"}`}
      className="mb-4"
    >
      {result.kept.length > 0 && (
        <>
          Kept because of sales or stock history: {shown}
          {more > 0 && ` and ${more} more`}. To hide one, open it, edit it and archive it.
        </>
      )}
    </Notice>
  );
}
