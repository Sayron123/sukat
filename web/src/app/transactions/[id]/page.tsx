import type { Metadata } from "next";
import { Suspense } from "react";

import { AppPage } from "@/components/app-page";
import { Loading } from "@/components/ui";

import { TransactionDetail } from "./transaction-detail";

export const metadata: Metadata = { title: "Transaction · Sukat" };

export default function TransactionPage({ params }: PageProps<"/transactions/[id]">) {
  return (
    <AppPage>
      <Suspense fallback={<Loading />}>
        <Detail params={params} />
      </Suspense>
    </AppPage>
  );
}

async function Detail({ params }: { params: PageProps<"/transactions/[id]">["params"] }) {
  const { id } = await params;
  return <TransactionDetail id={id} />;
}
