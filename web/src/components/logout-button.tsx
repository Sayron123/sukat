"use client";

import { hardNavigate } from "@/lib/hard-navigate";

export function LogoutButton() {
  async function logout() {
    await fetch("/api/auth/logout", { method: "POST" });
    hardNavigate("/login");
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
