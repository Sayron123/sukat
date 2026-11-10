import "server-only";

import { NextResponse, type NextRequest } from "next/server";

import { SESSION_COOKIE, SESSION_MAX_AGE, backendFetch, errorMessage, getToken } from "./backend";

/**
 * CSRF check: reject POSTs sent by other websites.
 *
 * Compares only the HOST of the browser's Origin header with the host this request was
 * sent to (x-forwarded-host when behind a proxy, else host). This is the same check
 * Next.js uses for Server Actions. Comparing the full origin would break behind an HTTPS
 * proxy, where the browser says "https://" but this server sees "http://".
 *
 * @returns true when there is no Origin header (non-browser clients, which cannot carry
 *   the victim's cookies anyway) or when the hosts match.
 */
export function isSameOrigin(req: NextRequest): boolean {
  const origin = req.headers.get("origin");
  if (origin === null) return true;
  const requestHost = req.headers.get("x-forwarded-host") ?? req.headers.get("host");
  if (!requestHost) return false;
  try {
    return new URL(origin).host === requestHost.split(",")[0].trim();
  } catch {
    return false; // "null" or a malformed Origin
  }
}

/**
 * The caller's IP chain, passed on so the API can rate-limit per IP. Only trustworthy
 * when a proxy in front of Next.js sets X-Forwarded-For (most hosts do); the API also
 * limits per email, which cannot be faked.
 */
function forwardedFor(req: NextRequest): Record<string, string> {
  const xff = req.headers.get("x-forwarded-for");
  return xff ? { "X-Forwarded-For": xff } : {};
}

export function setSessionCookie(response: NextResponse, token: string): void {
  response.cookies.set(SESSION_COOKIE, token, {
    httpOnly: true, // not readable by JavaScript (protects against XSS token theft)
    secure: process.env.NODE_ENV === "production", // HTTPS only in production
    sameSite: "lax", // not sent on cross-site POSTs (CSRF protection)
    path: "/",
    maxAge: SESSION_MAX_AGE,
  });
}

type Forwarded = { ok: true; data: unknown } | { ok: false; response: NextResponse };

async function forward(req: NextRequest, apiPath: string, token?: string): Promise<Forwarded> {
  if (!isSameOrigin(req)) {
    return { ok: false, response: NextResponse.json({ error: "Bad origin" }, { status: 403 }) };
  }

  let body: unknown;
  try {
    body = await req.json();
  } catch {
    return { ok: false, response: NextResponse.json({ error: "Invalid request" }, { status: 400 }) };
  }

  let res: Response;
  try {
    res = await backendFetch(apiPath, {
      method: "POST",
      body: JSON.stringify(body),
      headers: forwardedFor(req),
      token,
    });
  } catch {
    return { ok: false, response: NextResponse.json({ error: "API not reachable" }, { status: 502 }) };
  }

  const data: unknown = await res.json().catch(() => null);
  if (!res.ok) {
    return {
      ok: false,
      response: NextResponse.json(
        { error: errorMessage(data, "Something went wrong") },
        { status: res.status },
      ),
    };
  }
  return { ok: true, data };
}

/**
 * Forward a login/signup request to the API. On success, store the token in an
 * httpOnly cookie so browser JavaScript can never read it. The token is NOT returned.
 */
export async function forwardAuth(
  req: NextRequest,
  apiPath: string,
  options: { sendToken?: boolean } = {},
): Promise<NextResponse> {
  const result = await forward(req, apiPath, options.sendToken ? await getToken() : undefined);
  if (!result.ok) return result.response;

  const { access_token } = result.data as { access_token: string };
  const response = NextResponse.json({ ok: true });
  setSessionCookie(response, access_token);
  return response;
}

export async function forwardPublic(req: NextRequest, apiPath: string): Promise<NextResponse> {
  const result = await forward(req, apiPath);
  return result.ok ? NextResponse.json({ ok: true }) : result.response;
}
