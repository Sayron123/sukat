import type { Metadata } from "next";

import { AppPage } from "@/components/app-page";

import { ExportData } from "./export-data";

export const metadata: Metadata = { title: "Download store data · Sukat" };

export default function ExportPage() {
  return (
    <AppPage tab="more">
      <ExportData />
    </AppPage>
  );
}
