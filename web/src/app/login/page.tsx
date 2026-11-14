import type { Metadata } from "next";
import { Suspense } from "react";

import { AuthForm } from "@/components/auth-form";
import { Loading } from "@/components/ui";
import { googleClientId } from "@/lib/server/google";

export const metadata: Metadata = { title: "Log in · Sukat" };

type SearchParams = Promise<{ error?: string | string[] }>;

export default function LoginPage({ searchParams }: { searchParams: SearchParams }) {
  return (
    <Suspense fallback={<Loading />}>
      <LoginContent searchParams={searchParams} />
    </Suspense>
  );
}

async function LoginContent({ searchParams }: { searchParams: SearchParams }) {
  const { error } = await searchParams;
  const google = (await googleClientId()) ? { mode: "login" as const } : undefined;
  return (
    <AuthForm
      title="Sign in"
      subtitle="Sign in to open your store."
      mascot={160}
      signedOutText="You were signed out. Sign in again to open your store."
      endpoint="/api/auth/login"
      submitLabel="Sign in"
      alert={typeof error === "string" ? error : undefined}
      google={google}
      fields={[
        { name: "login", label: "Email or username", autoComplete: "username" },
        {
          name: "password",
          label: "Password",
          type: "password",
          autoComplete: "current-password",
        },
      ]}
      createAccount={{ prompt: "New to Sukat?", text: "Create account", href: "/signup" }}
      altLink={{ text: "Forgot your password?", href: "/forgot-password" }}
    />
  );
}
