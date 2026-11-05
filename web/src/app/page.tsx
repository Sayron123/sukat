import type { Metadata } from "next";

import { ActionDock } from "@/components/action-dock";
import { AppPage } from "@/components/app-page";

import { HomeScreen } from "./home-screen";
import { ScanReceiptButton } from "./scan-receipt-button";

export const metadata: Metadata = { title: "Sukat" };

export default function Home() {
  return (
    <AppPage tab="home">
      <HomeScreen />
      <ActionDock>
        <ScanReceiptButton />
      </ActionDock>
    </AppPage>
  );
}
