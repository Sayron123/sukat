import type { Metadata } from "next";

import { AppPage } from "@/components/app-page";
import { PageHeader } from "@/components/page-header";

import { PasswordForm } from "./password-form";

export const metadata: Metadata = { title: "Change password · Sukat" };

export default function PasswordPage() {
  return (
    <AppPage>
      <PageHeader title="Change password" back="/more/settings" />
      <PasswordForm />
    </AppPage>
  );
}
