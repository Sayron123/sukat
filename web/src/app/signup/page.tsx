import type { Metadata } from "next";

import { AuthForm } from "@/components/auth-form";

export const metadata: Metadata = { title: "Create your store · Sukat" };

export default function SignupPage() {
  return (
    <AuthForm
      title="Create your store"
      endpoint="/api/auth/signup"
      submitLabel="Create store"
      fields={[
        { name: "store_name", label: "Store name", autoComplete: "organization" },
        { name: "full_name", label: "Your name", autoComplete: "name" },
        { name: "email", label: "Email", type: "email", autoComplete: "email" },
        {
          name: "password",
          label: "Password (8+ characters)",
          type: "password",
          autoComplete: "new-password",
          minLength: 8,
        },
      ]}
      footer={{ text: "Already have an account?", href: "/login", link: "Log in" }}
    />
  );
}
