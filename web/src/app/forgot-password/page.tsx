import type { Metadata } from "next";

import { ForgotForm } from "./forgot-form";

export const metadata: Metadata = { title: "Forgot password · Sukat" };

export default function ForgotPasswordPage() {
  return <ForgotForm />;
}
