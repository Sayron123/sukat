import "server-only";

import { createHash, randomBytes, timingSafeEqual } from "node:crypto";

import type { NextRequest } from "next/server";

import { IS_PRODUCTION, backendFetch } from "./backend";

export const GOOGLE_COOKIE = "sukat_google";
export const GOOGLE_PATH = "/api/auth/google";
export const CALLBACK_PATH = `${GOOGLE_PATH}/callback`;
export const AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth";

export type GoogleMode = "login" | "signup" | "invite" | "connect";

export type GoogleTrip = {
  mode: GoogleMode;
  state: string;
  verifier: string;
  nonce: string;
  invite?: string;
};

export const TICKET_COOKIE = "sukat_google_ticket";

export type GoogleTicket = {
  mode: "signup" | "invite";
  ticket: string;
  email: string;
  name: string;
  account: boolean;
  invite?: string;
};

export const TICKET_COOKIE_OPTIONS = {
  httpOnly: true,
  secure: IS_PRODUCTION,
  sameSite: "lax" as const,
  path: "/",
  maxAge: 900,
};

export const COOKIE_OPTIONS = {
  httpOnly: true,
  secure: IS_PRODUCTION,
  sameSite: "lax" as const,
  path: GOOGLE_PATH,
  maxAge: 600,
};

export function random(bytes = 32): string {
  return randomBytes(bytes).toString("base64url");
}

export function challenge(verifier: string): string {
  return createHash("sha256").update(verifier).digest("base64url");
}

export function sameText(a: string, b: string): boolean {
  const x = Buffer.from(a);
  const y = Buffer.from(b);
  return x.length === y.length && timingSafeEqual(x, y);
}

export function packTrip(trip: GoogleTrip): string {
  return Buffer.from(JSON.stringify(trip)).toString("base64url");
}

export function packTicket(ticket: GoogleTicket): string {
  return Buffer.from(JSON.stringify(ticket)).toString("base64url");
}

export function unpackTicket(value: string | undefined): GoogleTicket | null {
  if (!value) return null;
  try {
    const ticket = JSON.parse(Buffer.from(value, "base64url").toString()) as GoogleTicket;
    const known = ticket.mode === "signup" || (ticket.mode === "invite" && typeof ticket.invite === "string");
    return known && typeof ticket.ticket === "string" && typeof ticket.email === "string" ? ticket : null;
  } catch {
    return null;
  }
}

export function unpackTrip(value: string | undefined): GoogleTrip | null {
  if (!value) return null;
  try {
    const trip = JSON.parse(Buffer.from(value, "base64url").toString()) as GoogleTrip;
    return typeof trip.state === "string" && typeof trip.verifier === "string" ? trip : null;
  } catch {
    return null;
  }
}

export function siteOrigin(req: NextRequest): string {
  const host = req.headers.get("x-forwarded-host")?.split(",")[0].trim() ?? req.headers.get("host");
  const proto = req.headers.get("x-forwarded-proto")?.split(",")[0].trim() ?? req.nextUrl.protocol.replace(":", "");
  return host ? `${proto}://${host}` : req.nextUrl.origin;
}

export function backTo(trip: Pick<GoogleTrip, "mode" | "invite">): string {
  if (trip.mode === "signup") return "/signup/manager";
  if (trip.mode === "invite" && trip.invite) return `/invite?token=${encodeURIComponent(trip.invite)}`;
  if (trip.mode === "connect") return "/more/settings";
  return "/login";
}

export async function googleClientId(): Promise<string | null> {
  try {
    const res = await backendFetch("/auth/google");
    if (!res.ok) return null;
    const data = (await res.json()) as { client_id: string | null };
    return data.client_id;
  } catch {
    return null;
  }
}
