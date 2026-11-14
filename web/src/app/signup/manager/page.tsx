import type { Metadata } from "next";
import { Suspense } from "react";

import { AuthForm } from "@/components/auth-form";
import { Loading } from "@/components/ui";
import { googleClientId } from "@/lib/server/google";

export const metadata: Metadata = { title: "Create your store · Sukat" };

type SearchParams = Promise<{ error?: string | string[] }>;

export default function ManagerSignupPage({ searchParams }: { searchParams: SearchParams }) {
  return (
    <Suspense fallback={<Loading />}>
      <SignupContent searchParams={searchParams} />
    </Suspense>
  );
}

async function SignupContent({ searchParams }: { searchParams: SearchParams }) {
  const { error } = await searchParams;
  const google = (await googleClientId()) ? { mode: "signup" as const } : undefined;
  return (
    <AuthForm
      alert={typeof error === "string" ? error : undefined}
      google={google}
      title="Set up your store"
      subtitle="Set up your store and your manager account."
      mascot={104}
      endpoint="/api/auth/signup"
      submitLabel="Create store"
      fields={[
        {
          name: "store_name",
          label: "Store name",
          autoComplete: "organization",
          placeholder: "Hardware (Branch)",
          section: "Your store",
        },
        {
          name: "store_address",
          label: "Store address (optional)",
          autoComplete: "street-address",
          maxLength: 300,
          optional: true,
          section: "Your store",
        },
        { name: "full_name", label: "Your name", autoComplete: "name", section: "Your account" },
        {
          name: "email",
          label: "Email",
          type: "email",
          autoComplete: "email",
          hint: "You will use this email to sign in.",
          section: "Your account",
        },
        {
          name: "password",
          label: "Password",
          type: "new-password",
          section: "Your account",
        },
      ]}
      footer={{ text: "Already have an account? Sign in", href: "/login" }}
      back="/signup"
      agreement
    />
  );
}
