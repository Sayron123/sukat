import type { Metadata } from "next";
import { redirect } from "next/navigation";

import { AppPage } from "@/components/app-page";
import { PageHeader } from "@/components/page-header";
import { Notice } from "@/components/ui";
import { backendFetch, getToken } from "@/lib/server/backend";
import type { Me } from "@/lib/types";

import { InviteForm } from "../invite-form";

export const metadata: Metadata = { title: "Invite someone · Sukat" };

export default function InvitePage() {
  return (
    <AppPage>
      <InviteContent />
    </AppPage>
  );
}

async function InviteContent() {
  const token = await getToken();
  if (!token) redirect("/login");

  let res: Response;
  try {
    res = await backendFetch("/auth/me", { token });
  } catch {
    return (
      <>
        <PageHeader title="Invite someone" back="/staff" />
        <Notice title="API not reachable">
          The Sukat server is not responding. Check that it is running, then reload this page.
        </Notice>
      </>
    );
  }
  if (res.status === 401) redirect("/login");
  if (!res.ok) throw new Error("Could not load your account");
  const me = (await res.json()) as Me;
  if (me.role === "member") redirect("/staff");

  return (
    <>
      <PageHeader title="Invite someone" back="/staff" />
      <InviteForm inviterRole={me.role} />
    </>
  );
}
