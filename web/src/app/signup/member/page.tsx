import type { Metadata } from "next";

import { AuthShell } from "@/components/auth-form";
import { Notice } from "@/components/ui";

import { JoinForm } from "./join-form";

export const metadata: Metadata = { title: "Join your store · Sukat" };

export default function MemberSignupPage() {
  return (
    <AuthShell title="Join your store" subtitle="Members join with an invite link from their manager." back="/signup">
      <Notice icon="users" title="No link yet?" className="mb-[22px]">
        Ask your manager to create one on the Staff screen. The link sets your role.
      </Notice>
      <JoinForm />
    </AuthShell>
  );
}
