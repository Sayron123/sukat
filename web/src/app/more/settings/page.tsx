import type { Metadata } from "next";

import { AppPage } from "@/components/app-page";
import { PageHeader } from "@/components/page-header";
import { googleClientId } from "@/lib/server/google";

import { SettingsList } from "./settings-list";

export const metadata: Metadata = { title: "Settings · Sukat" };

export default async function SettingsPage() {
  const google = (await googleClientId()) !== null;
  return (
    <AppPage tab="more">
      <PageHeader title="Settings" back="/more" />
      <SettingsList google={google} />
    </AppPage>
  );
}
