import type { Metadata } from "next";

import { AppPage } from "@/components/app-page";

import { ScanFlow } from "./scan-flow";

export const metadata: Metadata = { title: "Scan stock in · Sukat" };

export default function ScanPage() {
  return (
    <AppPage>
      <ScanFlow mode="stock_in" />
    </AppPage>
  );
}
