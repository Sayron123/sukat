import type { Metadata } from "next";

import { ActionDock } from "@/components/action-dock";
import { AppPage } from "@/components/app-page";
import { ScanButton } from "@/components/scan-button";

import { HomeScreen } from "./home-screen";

export const metadata: Metadata = { title: "Sukat" };

export default function Home() {
  return (
    <AppPage tab="home">
      <HomeScreen />
      <ActionDock>
        <ScanButton href="/scan/sale" />
      </ActionDock>
    </AppPage>
  );
}
