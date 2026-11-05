import type { Metadata } from "next";

import { AppPage } from "@/components/app-page";

import { TransactionList } from "./transaction-list";

export const metadata: Metadata = { title: "History · Sukat" };

export default function TransactionsPage() {
  return (
    <AppPage>
      <TransactionList />
    </AppPage>
  );
}
