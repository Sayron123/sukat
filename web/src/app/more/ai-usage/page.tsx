import type { Metadata } from "next";

import { AppPage } from "@/components/app-page";
import { PageHeader } from "@/components/page-header";

import { UsageView } from "./usage-view";

export const metadata: Metadata = { title: "AI usage · Sukat" };

export default function AiUsagePage() {
  return (
    <AppPage>
      <PageHeader title="AI usage" back="/more" />
      <UsageView />
    </AppPage>
  );
}
