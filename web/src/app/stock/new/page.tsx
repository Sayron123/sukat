import type { Metadata } from "next";

import { AppPage } from "@/components/app-page";
import { RequireWriter } from "@/components/require-writer";

import { ProductForm } from "../product-form";

export const metadata: Metadata = { title: "Add product · Sukat" };

export default function NewProductPage() {
  return (
    <AppPage active="stock">
      <RequireWriter>
        <ProductForm />
      </RequireWriter>
    </AppPage>
  );
}
