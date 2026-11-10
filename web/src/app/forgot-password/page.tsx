import type { Metadata } from "next";

import { AuthForm } from "@/components/auth-form";

export const metadata: Metadata = { title: "Forgot password · Sukat" };

export default function ForgotPasswordPage() {
  return (
    <AuthForm
      title="Forgot your password?"
      subtitle="Enter your email and we will send you a link to set a new one."
      endpoint="/api/auth/forgot-password"
      submitLabel="Send Link"
      done="If that email has an account, a link is on its way."
      fields={[{ name: "email", label: "Email", type: "email", autoComplete: "email" }]}
      footer={{ text: "Back to sign in", href: "/login" }}
      back="/login"
    />
  );
}
