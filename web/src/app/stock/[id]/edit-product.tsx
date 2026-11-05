"use client";

import { useEffect, useState } from "react";

import { ApiError, api } from "@/lib/api-client";
import type { Product } from "@/lib/types";

import { ProductForm } from "../product-form";

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

  if (error) return <p className="text-red">{error}</p>;
  if (!product) return <p className="text-muted">Loading…</p>;
  return <ProductForm product={product} />;
}
