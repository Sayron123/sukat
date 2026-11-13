import type { Metadata } from "next";

import { AuthForm } from "@/components/auth-form";

export const metadata: Metadata = { title: "Create your store · Sukat" };

export default function ManagerSignupPage() {
  return (
    <AuthForm
      title="Set up your store"
      subtitle="Set up your store and your manager account."
      mascot={100}
      endpoint="/api/auth/signup"
      submitLabel="Create Store"
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
