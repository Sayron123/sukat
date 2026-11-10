import type { Metadata } from "next";
import { Suspense } from "react";

import { TokenForm } from "@/components/token-form";
import { Loading } from "@/components/ui";

export const metadata: Metadata = { title: "New password · Sukat", referrer: "no-referrer" };

export default function ResetPasswordPage() {
  return (
    <Suspense fallback={<Loading />}>
      <TokenForm
        title="Set a new password"
        subtitle="You will sign in with this password from now on."
        endpoint="/api/auth/reset-password"
        submitLabel="Save Password"
        done="Your password is changed. Sign in with your new password."
        fields={[{ name: "new_password", label: "New password", type: "new-password" }]}
        footer={{ text: "Back to sign in", href: "/login" }}
      />
    </Suspense>
  );
}
