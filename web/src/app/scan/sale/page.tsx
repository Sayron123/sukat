import type { Metadata } from "next";

import { AppPage } from "@/components/app-page";

import { ScanFlow } from "../scan-flow";

export const metadata: Metadata = { title: "Scan receipt · Sukat" };

export default function ScanSalePage() {
  return (
    <AppPage active="scan">
      <ScanFlow mode="sale" />
    </AppPage>
  );
}
