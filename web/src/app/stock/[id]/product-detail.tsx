"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { ConfirmDialog } from "@/components/confirm-dialog";
import { Icon } from "@/components/icons";
import { PageHeader, headerIconClass } from "@/components/page-header";
import { Badge, Button, Card, Loading, Pager } from "@/components/ui";
import { ApiError, api } from "@/lib/api-client";
import { formatPeso, formatQty, formatShortWhen } from "@/lib/format";
import { KIND_TITLE } from "@/lib/labels";
import { type Me, type MovementPage, type MovementRow, type Product, canEditProducts } from "@/lib/types";

/** One product: stock, price, low-stock alert, and every stock change (newest first). */
export function ProductDetail({ id }: { id: string }) {
  const [product, setProduct] = useState<Product | null>(null);
  const [me, setMe] = useState<Me | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [page, setPage] = useState(1);
  const [history, setHistory] = useState<MovementPage | null | "error">(null);
  const router = useRouter();
  const [confirming, setConfirming] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);

  useEffect(() => {
    api<Me>("auth/me").then(setMe, () => {});
    api<Product>(`products/${encodeURIComponent(id)}`).then(setProduct, (e: unknown) =>
      setError(e instanceof ApiError && (e.status === 404 || e.status === 422) ? "Product not found." : "Could not load product."),
    );
  }, [id]);

  useEffect(() => {
    let stale = false;
    api<MovementPage>(`reports/products/${encodeURIComponent(id)}/history?page=${page}`).then(
      (res) => !stale && setHistory(res),
      () => !stale && setHistory("error"),
    );
    return () => {
      stale = true;
    };
  }, [id, page]);

  async function deleteProduct() {
    setDeleting(true);
    setDeleteError(null);
    try {
      await api(`products/${encodeURIComponent(id)}`, { method: "DELETE" });
      router.replace("/stock");
    } catch (e) {
      setDeleteError(e instanceof ApiError ? e.message : "Could not delete this product.");
      setConfirming(false);
      setDeleting(false);
    }
  }

  if (error)
    return (
      <>
        <PageHeader title="Product" back="/stock" />
        <p className="text-red">{error}</p>
      </>
    );
  if (!product) return <Loading />;
  const canDelete = me?.role === "manager";

  return (
    <>
      <PageHeader
        eyebrow={product.category}
        title={product.name}
        back="/stock"
        action={
          canEditProducts(me?.role) && (
            <Link href={`/stock/${product.id}/edit`} aria-label="Edit product" className={headerIconClass}>
              <Icon name="edit" size={22} />
            </Link>
          )
        }
      />

      {product.archived && (
        <p className="mb-3">
          <Badge>Archived</Badge>
        </p>
      )}
      <div className="mb-3 rounded-card bg-surface p-4">
        <span className="flex items-center justify-between text-sm text-muted">
          <span>In stock</span>
          {product.is_low_stock && <Badge tone="red">Low</Badge>}
        </span>
        <strong className="mt-3 block text-[32px] leading-tight text-text">
          {formatQty(product.stock_qty)} <span className="text-base font-semibold text-muted">{product.base_unit}</span>
        </strong>
      </div>
      <div className={`${canDelete ? "mb-3" : "mb-8"} grid grid-cols-2 gap-3`}>
        <Card>
          <p className="text-[13px] text-muted">Price</p>
          <p className="mt-1 font-bold text-text">
            {formatPeso(product.price_centavos)}
            {product.price_centavos !== null && <span className="font-normal text-muted">/{product.base_unit}</span>}
          </p>
        </Card>
        <Card>
          <p className="text-[13px] text-muted">Low stock alert</p>
          <p className="mt-1 font-bold text-text">
            {product.low_stock_level === null ? "Off" : `${formatQty(product.low_stock_level)} ${product.base_unit}`}
          </p>
        </Card>
      </div>

      {canDelete && (
        <div className="mb-8">
          {deleteError && (
            <p role="alert" className="mb-3 text-sm text-red">
              {deleteError}
            </p>
          )}
          <Button type="button" variant="danger" icon="trash" onClick={() => setConfirming(true)}>
            Delete product
          </Button>
        </div>
      )}

      <h2 className="mb-3 text-lg font-bold text-text">Stock history</h2>
      {history === null ? (
        <p className="text-muted">Loading…</p>
      ) : history === "error" ? (
        <p className="text-red">Could not load the history.</p>
      ) : history.items.length === 0 ? (
        <Card className="text-muted">No stock changes yet.</Card>
      ) : (
        <>
          <ul className="mb-5 border-t border-border">
            {history.items.map((m) => (
              <MovementLine key={m.id} m={m} />
            ))}
          </ul>
          <Pager page={history.page} pages={history.pages} onPage={setPage} />
        </>
      )}

      <ConfirmDialog
        open={confirming}
        title={`Delete ${product.name}?`}
        confirmLabel="Delete"
        danger
        busy={deleting}
        onConfirm={deleteProduct}
        onCancel={() => setConfirming(false)}
      >
        This can&apos;t be undone.
      </ConfirmDialog>
    </>
  );
}

function MovementLine({ m }: { m: MovementRow }) {
  const qty = formatQty(m.qty_change.replace("-", ""));
  const out = m.qty_change.startsWith("-");
  return (
    <li>
      <Link
        href={`/transactions/${m.transaction_id}`}
        className="flex min-h-[72px] items-center gap-2 border-b border-border py-2.5"
      >
        <div className="min-w-0 flex-1">
          <b className="block text-base text-text">{KIND_TITLE[m.kind]}</b>
          <small className="mt-1 block truncate text-sm text-muted">
            {formatShortWhen(m.created_at)}
            {m.created_by_name && ` · ${m.created_by_name}`}
          </small>
        </div>
        <div className="shrink-0 text-right">
          <strong className={`block text-base ${out ? "text-text" : "text-green-text"}`}>
            {out ? "−" : "+"} {qty} {m.base_unit}
          </strong>
          <small className="mt-1 block text-sm text-muted">
            stock {formatQty(m.stock_after)}
          </small>
        </div>
      </Link>
    </li>
  );
}
