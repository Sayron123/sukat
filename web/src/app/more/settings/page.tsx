import type { Metadata } from "next";

import { AppPage } from "@/components/app-page";
import { PageHeader } from "@/components/page-header";

import { SettingsList } from "./settings-list";

export const metadata: Metadata = { title: "Settings · Sukat" };

export default function SettingsPage() {
  return (
    <AppPage tab="more">
      <PageHeader title="Settings" back="/more" />
      <SettingsList />
    </AppPage>
  );
}
