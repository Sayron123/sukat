import type { Metadata } from "next";

import { AppPage } from "@/components/app-page";

import { StockList } from "./stock-list";

export const metadata: Metadata = { title: "Stock · Sukat" };

export default function StockPage() {
  return (
    <AppPage active="stock">
      <StockList />
    </AppPage>
  );
}
