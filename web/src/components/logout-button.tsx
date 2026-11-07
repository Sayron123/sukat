"use client";

import { hardNavigate } from "@/lib/hard-navigate";
import { clearSessionData } from "@/lib/session-data";

import { ghostButtonClass } from "./ui";

export function LogoutButton() {
  async function logout() {
    await fetch("/api/auth/logout", { method: "POST" });
    clearSessionData(); // the next person on this phone starts with an empty chat
    hardNavigate("/login");
  }
  return (
    <button type="button" onClick={logout} className={`${ghostButtonClass} w-full`}>
      Sign out
    </button>
  );
}
