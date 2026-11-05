"use client";

import { useEffect, useState } from "react";

import { PageHeader } from "@/components/page-header";
import { Loading } from "@/components/ui";
import { ApiError, api } from "@/lib/api-client";
import type { Product } from "@/lib/types";

import { ProductForm } from "../../product-form";

export function EditProduct({ id }: { id: string }) {
  const [product, setProduct] = useState<Product | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api<Product>(`products/${encodeURIComponent(id)}`).then(setProduct, (e: unknown) =>
      setError(
        e instanceof ApiError && (e.status === 404 || e.status === 422)
          ? "Product not found."
          : "Could not load product.",
      ),
    );
  }, [id]);

  if (error)
    return (
      <>
        <PageHeader eyebrow="Product details" title="Edit product" back={`/stock/${id}`} />
        <p className="text-red">{error}</p>
      </>
    );
  if (!product) return <Loading />;
  return <ProductForm product={product} />;
}
