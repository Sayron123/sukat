import type { Metadata } from "next";

import { AppPage } from "@/components/app-page";
import { PageHeader } from "@/components/page-header";

import { StoreForm } from "./store-form";

export const metadata: Metadata = { title: "Store details · Sukat" };

export default function StorePage() {
  return (
    <AppPage>
      <PageHeader title="Store details" back="/more/settings" />
      <StoreForm />
    </AppPage>
  );
}
