"use client";

import { hardNavigate } from "@/lib/hard-navigate";

import { ghostButtonClass } from "./ui";

export function LogoutButton() {
  async function logout() {
    await fetch("/api/auth/logout", { method: "POST" });
    hardNavigate("/login");
  }
  return (
    <button type="button" onClick={logout} className={`${ghostButtonClass} w-full`}>
      Sign out
    </button>
  );
}
