import type { Metadata } from "next";

import { AppPage } from "@/components/app-page";
import { PageHeader } from "@/components/page-header";
import { Card } from "@/components/ui";

import { NameForm } from "./name-form";
import { PasswordForm } from "./password-form";
import { ThemePicker } from "./theme-picker";

export const metadata: Metadata = { title: "Settings · Sukat" };

export default function SettingsPage() {
  return (
    <AppPage>
      <PageHeader title="Settings" back="/more" />
      <div className="flex flex-col gap-4">
        <Card>
          <h2 className="mb-4 text-base font-bold text-text">Your name</h2>
          <NameForm />
        </Card>
        <Card>
          <h2 className="mb-4 text-base font-bold text-text">Password</h2>
          <PasswordForm />
        </Card>
        <Card>
          <h2 className="mb-4 text-base font-bold text-text">Appearance</h2>
          <ThemePicker />
        </Card>
      </div>
    </AppPage>
  );
}
