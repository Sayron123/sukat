"use client";

import { useSearchParams } from "next/navigation";
import type { ComponentProps } from "react";

import { AuthForm } from "./auth-form";

export function TokenForm(props: Omit<ComponentProps<typeof AuthForm>, "extra">) {
  const token = useSearchParams().get("token") ?? "";
  return <AuthForm {...props} extra={{ token }} />;
}
