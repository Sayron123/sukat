import type { Metadata } from "next";

import { AuthForm } from "@/components/auth-form";

export const metadata: Metadata = { title: "Log in · Sukat" };

export default function LoginPage() {
  return (
    <AuthForm
      title="Log in"
      endpoint="/api/auth/login"
      submitLabel="Log in"
      fields={[
        { name: "email", label: "Email", type: "email", autoComplete: "email" },
        {
          name: "password",
          label: "Password",
          type: "password",
          autoComplete: "current-password",
        },
      ]}
      footer={{ text: "New to Sukat?", href: "/signup", link: "Create a store" }}
    />
  );
}
