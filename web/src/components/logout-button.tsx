"use client";

import { useRouter } from "next/navigation";

export function LogoutButton() {
  const router = useRouter();
  async function logout() {
    await fetch("/api/auth/logout", { method: "POST" });
    router.push("/login");
    router.refresh();
  }
  return (
    <button
      onClick={logout}
      className="h-11 rounded-button border border-border bg-background px-4 text-sm font-medium text-text hover:bg-surface"
    >
      Log out
    </button>
  );
}
