import type { Metadata } from "next";
import { Suspense } from "react";

import { TokenForm } from "@/components/token-form";
import { Loading } from "@/components/ui";

export const metadata: Metadata = { title: "Confirm email · Sukat", referrer: "no-referrer" };

export default function VerifyEmailPage() {
  return (
    <Suspense fallback={<Loading />}>
      <TokenForm
        title="Confirm your email"
        subtitle="This unlocks photo reading and the AI assistant."
        endpoint="/api/auth/verify-email"
        submitLabel="Confirm Email"
        done="Your email is confirmed."
        fields={[]}
        footer={{ text: "Go to Sukat", href: "/" }}
      />
    </Suspense>
  );
}
