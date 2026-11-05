import type { Metadata } from "next";

import { AppPage } from "@/components/app-page";
import { RequireWriter } from "@/components/require-writer";

import { ImportCatalog } from "./import-catalog";

export const metadata: Metadata = { title: "Import starter items · Sukat" };

export default function ImportPage() {
  return (
    <AppPage>
      <RequireWriter>
        <ImportCatalog />
      </RequireWriter>
    </AppPage>
  );
}
