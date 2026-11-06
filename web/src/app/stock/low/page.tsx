import type { Metadata } from "next";

import { AppPage } from "@/components/app-page";

import { LowStockList } from "./low-stock-list";

export const metadata: Metadata = { title: "Low stock · Sukat" };

export default function LowStockPage() {
  return (
    <AppPage>
      <LowStockList />
    </AppPage>
  );
}
