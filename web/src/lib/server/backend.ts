import "server-only";

import { cookies } from "next/headers";

const IS_PRODUCTION = process.env.NODE_ENV === "production";

export const SESSION_COOKIE = IS_PRODUCTION ? "__Host-sukat_session" : "sukat_session";

export const SESSION_COOKIE_OPTIONS = {
  httpOnly: true,
  secure: IS_PRODUCTION,
  sameSite: "lax",
  path: "/",
} as const;

export const SESSION_MAX_AGE = 400 * 24 * 60 * 60;

/** Backend base URL, used only on the server. */
export const API_URL = process.env.API_URL ?? process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

/** Version prefix of every API path (only /health lives outside it). */
export const API_PREFIX = "/v1";

export function clientIpHeaders(forwardedFor: string | null): Record<string, string> {
  const secret = process.env.INTERNAL_API_SECRET;
  const ip = forwardedFor?.split(",").at(-1)?.trim();
  return secret && ip ? { "X-Sukat-Proxy-Secret": secret, "X-Sukat-Client-IP": ip } : {};
}

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
