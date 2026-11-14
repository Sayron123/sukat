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
      submitLabel="Sign in"
      fields={[
        { name: "email", label: "Email", type: "email", autoComplete: "email" },
        {
          name: "password",
          label: "Password",
          type: "password",
          autoComplete: "current-password",
        },
      ]}
      createAccount={{ prompt: "New to Sukat?", text: "Create a store account", href: "/signup/manager" }}
      note="Staff member? Ask your store manager for your sign-in details."
      altLink={{ text: "Forgot your password?", href: "/forgot-password" }}
    />
  );
}
