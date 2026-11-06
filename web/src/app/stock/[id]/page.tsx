import type { Metadata } from "next";
import { Suspense } from "react";

import { AppPage } from "@/components/app-page";
import { Loading } from "@/components/ui";

import { ProductDetail } from "./product-detail";

export const metadata: Metadata = { title: "Product · Sukat" };

export default function ProductPage({ params }: PageProps<"/stock/[id]">) {
  return (
    <AppPage>
      <Suspense fallback={<Loading />}>
        <Loader params={params} />
      </Suspense>
    </AppPage>
  );
}

async function Loader({ params }: { params: PageProps<"/stock/[id]">["params"] }) {
  const { id } = await params;
  return <ProductDetail id={id} />;
}
