import type { Metadata } from "next";
import { Suspense } from "react";

import { AppPage } from "@/components/app-page";
import { Loading } from "@/components/ui";
import { RequireWriter } from "@/components/require-writer";

import { EditProduct } from "./edit-product";

export const metadata: Metadata = { title: "Edit product · Sukat" };

export default function EditProductPage({ params }: PageProps<"/stock/[id]/edit">) {
  return (
    <AppPage>
      <Suspense fallback={<Loading />}>
        <EditProductLoader params={params} />
      </Suspense>
    </AppPage>
  );
}

async function EditProductLoader({ params }: { params: PageProps<"/stock/[id]/edit">["params"] }) {
  const { id } = await params;
  return (
    <RequireWriter>
      <EditProduct id={id} />
    </RequireWriter>
  );
}
