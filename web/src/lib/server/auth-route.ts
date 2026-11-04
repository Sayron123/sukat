import "server-only";

import { NextResponse, type NextRequest } from "next/server";

import { SESSION_COOKIE, backendFetch, errorMessage } from "./backend";

/** Reject cross-site form posts: the request must come from this site's own pages. */
export function isSameOrigin(req: NextRequest): boolean {
  const origin = req.headers.get("origin");
  return origin === null || origin === req.nextUrl.origin;
}

/**
 * Forward a login/signup request to the API. On success, store the token in an
 * httpOnly cookie so browser JavaScript can never read it. The token is NOT returned.
 */
export async function forwardAuth(req: NextRequest, apiPath: string): Promise<NextResponse> {
  if (!isSameOrigin(req)) {
    return NextResponse.json({ error: "Bad origin" }, { status: 403 });
  }

  let body: unknown;
  try {
    body = await req.json();
  } catch {
    return NextResponse.json({ error: "Invalid request" }, { status: 400 });
  }

  let res: Response;
  try {
    res = await backendFetch(apiPath, { method: "POST", body: JSON.stringify(body) });
  } catch {
    return NextResponse.json({ error: "API not reachable" }, { status: 502 });
  }

  const data: unknown = await res.json().catch(() => null);
  if (!res.ok) {
    return NextResponse.json(
      { error: errorMessage(data, "Something went wrong") },
      { status: res.status },
    );
  }

  const { access_token, expires_in } = data as { access_token: string; expires_in: number };
  const response = NextResponse.json({ ok: true });
  response.cookies.set(SESSION_COOKIE, access_token, {
    httpOnly: true, // not readable by JavaScript (protects against XSS token theft)
    secure: process.env.NODE_ENV === "production", // HTTPS only in production
    sameSite: "lax", // not sent on cross-site POSTs (CSRF protection)
    path: "/",
    maxAge: expires_in,
  });
  return response;
}
