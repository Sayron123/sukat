"use client";

import { hardNavigate } from "@/lib/hard-navigate";
import { clearSessionData } from "@/lib/session-data";

import { Icon } from "./icons";

export function LogoutButton() {
  async function logout() {
    await fetch("/api/auth/logout", { method: "POST" });
    clearSessionData(); // the next person on this phone starts with an empty chat
    hardNavigate("/login");
  }
  return (
    <button
      type="button"
      onClick={logout}
      className="flex h-12 w-full items-center justify-center gap-2 rounded-button border border-line bg-surface px-4 text-[15px] font-semibold text-red hover:bg-red-soft"
    >
      <Icon name="logout" size={20} />
      Sign out
    </button>
  );
}
