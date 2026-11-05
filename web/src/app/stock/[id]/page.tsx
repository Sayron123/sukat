import type { Metadata } from "next";
import { Suspense } from "react";

import { AppPage } from "@/components/app-page";
import { RequireWriter } from "@/components/require-writer";

import { EditProduct } from "./edit-product";

export const metadata: Metadata = { title: "Edit product · Sukat" };

export default function EditProductPage({ params }: PageProps<"/stock/[id]">) {
  return (
    <AppPage active="stock">
      <Suspense fallback={<p className="text-muted">Loading…</p>}>
        <EditProductLoader params={params} />
      </Suspense>
    </AppPage>
  );
}

async function EditProductLoader({ params }: { params: PageProps<"/stock/[id]">["params"] }) {
  const { id } = await params;
  return (
    <RequireWriter>
      <EditProduct id={id} />
    </RequireWriter>
  );
}
