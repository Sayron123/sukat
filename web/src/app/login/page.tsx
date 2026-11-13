import type { Metadata } from "next";

import { AuthForm } from "@/components/auth-form";

export const metadata: Metadata = { title: "Log in · Sukat" };

export default function LoginPage() {
  return (
    <AuthForm
      title="Sign in"
      subtitle="Sign in to open your store."
      mascot={160}
      signedOutText="You were signed out. Sign in again to open your store."
      endpoint="/api/auth/login"
      submitLabel="Sign In"
      fields={[
        { name: "email", label: "Email", type: "email", autoComplete: "email" },
        {
          name: "password",
          label: "Password",
          type: "password",
          autoComplete: "current-password",
        },
      ]}
      footer={{ text: "New here? Create an account", href: "/signup" }}
      altLink={{ text: "Forgot your password?", href: "/forgot-password" }}
    />
  );
}
