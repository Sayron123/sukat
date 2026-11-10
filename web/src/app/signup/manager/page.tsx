import type { Metadata } from "next";

import { AuthForm } from "@/components/auth-form";

export const metadata: Metadata = { title: "Create your store · Sukat" };

export default function ManagerSignupPage() {
  return (
    <AuthForm
      title="Set up your store"
      subtitle="Create your store and your manager account."
      endpoint="/api/auth/signup"
      submitLabel="Create Store"
      fields={[
        { name: "store_name", label: "Store name", autoComplete: "organization" },
        {
          name: "store_address",
          label: "Store address (optional)",
          autoComplete: "street-address",
          maxLength: 300,
          optional: true,
        },
        { name: "full_name", label: "Your name", autoComplete: "name" },
        { name: "email", label: "Email", type: "email", autoComplete: "email" },
        {
          name: "password",
          label: "Password",
          type: "new-password",
        },
      ]}
      footer={{ text: "Already have an account? Sign in", href: "/login" }}
      back="/signup"
    />
  );
}
