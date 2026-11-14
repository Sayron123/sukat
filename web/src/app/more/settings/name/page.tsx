import type { Metadata } from "next";

import { AppPage } from "@/components/app-page";
import { PageHeader } from "@/components/page-header";

import { NameForm } from "./name-form";

export const metadata: Metadata = { title: "Your name · Sukat" };

export default function NamePage() {
  return (
    <AppPage>
      <PageHeader title="Your name" back="/more/settings" />
      <NameForm />
    </AppPage>
  );
}
