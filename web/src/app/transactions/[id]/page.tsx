import type { Metadata } from "next";
import { Suspense } from "react";

import { AppPage } from "@/components/app-page";

import { TransactionDetail } from "./transaction-detail";

export const metadata: Metadata = { title: "Transaction · Sukat" };

export default function TransactionPage({ params }: PageProps<"/transactions/[id]">) {
  return (
    <AppPage active="history">
      <Suspense fallback={<p className="text-muted">Loading…</p>}>
        <Detail params={params} />
      </Suspense>
    </AppPage>
  );
}

async function Detail({ params }: { params: PageProps<"/transactions/[id]">["params"] }) {
  const { id } = await params;
  return <TransactionDetail id={id} />;
}
