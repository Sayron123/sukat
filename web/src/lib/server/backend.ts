import "server-only";

import { cookies } from "next/headers";

/** Name of the httpOnly cookie that holds the API access token. */
export const SESSION_COOKIE = "sukat_session";

/** Backend base URL, used only on the server. */
export const API_URL = process.env.API_URL ?? process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

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
  return fetch(`${API_URL}${path}`, {
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
