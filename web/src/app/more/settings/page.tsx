import type { Metadata } from "next";

import { AppPage } from "@/components/app-page";
import { PageHeader } from "@/components/page-header";
import { googleClientId } from "@/lib/server/google";

import { SettingsList } from "./settings-list";

export const metadata: Metadata = { title: "Settings · Sukat" };

export default function SettingsPage() {
  return (
    <AppPage tab="more">
      <PageHeader title="Settings" back="/more" />
      <SettingsContent />
    </AppPage>
  );
}

async function SettingsContent() {
  const google = (await googleClientId()) !== null;
  return <SettingsList google={google} />;
}
