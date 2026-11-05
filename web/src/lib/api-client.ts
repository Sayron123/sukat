"use client";

import { errorMessage } from "./errors";
import { hardNavigate } from "./hard-navigate";

export class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
  ) {
    super(message);
  }
}

/**
 * Call the API from a client component through the same-origin proxy.
 * On 401 (no session / expired) it sends the user to the login page.
 *
 * @throws ApiError with a readable message for any non-2xx response
 */
export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`/api/backend/${path}`, {
      ...init,
      headers: { "Content-Type": "application/json", ...init.headers },
    });
  } catch {
    throw new ApiError("Network error. Check your connection.", 0);
  }
  if (res.status === 401) {
    hardNavigate("/login");
    throw new ApiError("Please log in again.", 401);
  }
  const body: unknown = await res.json().catch(() => null);
  if (!res.ok) throw new ApiError(errorMessage(body, "Something went wrong"), res.status);
  return body as T;
}
