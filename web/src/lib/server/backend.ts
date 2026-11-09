import "server-only";

import { cookies } from "next/headers";

const IS_PRODUCTION = process.env.NODE_ENV === "production";

/**
 * Name of the httpOnly cookie that holds the API access token. In production the
 * "__Host-" prefix makes the browser refuse it unless it is Secure, has path "/" and no
 * Domain, so no subdomain or plain-HTTP page can set or overwrite it.
 */
export const SESSION_COOKIE = IS_PRODUCTION ? "__Host-sukat_session" : "sukat_session";

/** Flags for the session cookie. Used when it is set and when it is cleared. */
export const SESSION_COOKIE_OPTIONS = {
  httpOnly: true, // not readable by JavaScript (protects against XSS token theft)
  secure: IS_PRODUCTION, // HTTPS only in production
  sameSite: "lax", // not sent on cross-site POSTs (CSRF protection)
  path: "/",
} as const;

/** Backend base URL, used only on the server. */
export const API_URL = process.env.API_URL ?? process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

/** Version prefix of every API path (only /health lives outside it). */
export const API_PREFIX = "/v1";

/** Read the access token from the httpOnly cookie (server only). */
export async function getToken(): Promise<string | undefined> {
  return (await cookies()).get(SESSION_COOKIE)?.value;
}

/** Call the backend from the server, adding the bearer token when there is one. */
export async function backendFetch(
  path: string,
  init: RequestInit & { token?: string } = {},
): Promise<Response> {
  const { token, headers, ...rest } = init;
  return fetch(`${API_URL}${API_PREFIX}${path}`, {
    ...rest,
    cache: "no-store",
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...headers,
    },
  });
}

export { errorMessage } from "@/lib/errors";
