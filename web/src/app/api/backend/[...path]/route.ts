import { NextResponse, type NextRequest } from "next/server";

import { isSameOrigin } from "@/lib/server/auth-route";
import { API_PREFIX, API_URL, getToken } from "@/lib/server/backend";

/**
 * Same-origin proxy from the browser to the FastAPI backend.
 *
 * The access token lives in an httpOnly cookie that browser code cannot read, so
 * client components call /api/backend/<path> and this handler adds the token.
 * Only the API areas the web app uses are allowed through.
 */
const ALLOWED_PREFIXES = [
  "products",
  "auth/me",
  "scans",
  "transactions",
  "reports",
  "insights",
  "exports",
];

/**
 * Only plain segments like "products" or a UUID. Next.js decodes %2F and %2E inside a
 * segment, so without this "products/..%2F..%2Fstaff" would pass the prefix check and
 * fetch() would then resolve the ".." and reach /staff.
 */
const SAFE_SEGMENT = /^[A-Za-z0-9_-]+$/;

async function proxy(req: NextRequest, ctx: RouteContext<"/api/backend/[...path]">) {
  const { path } = await ctx.params;
  const joined = path.join("/");
  if (
    !path.every((segment) => SAFE_SEGMENT.test(segment)) ||
    !ALLOWED_PREFIXES.some((p) => joined === p || joined.startsWith(`${p}/`))
  ) {
    return NextResponse.json({ detail: "Not found" }, { status: 404 });
  }
  // CSRF: writes must come from our own pages.
  if (req.method !== "GET" && !isSameOrigin(req)) {
    return NextResponse.json({ detail: "Bad origin" }, { status: 403 });
  }
  const token = await getToken();
  if (!token) {
    return NextResponse.json({ detail: "Not authenticated" }, { status: 401 });
  }

  const requestId = crypto.randomUUID().replaceAll("-", "");
  let res: Response;
  try {
    res = await fetch(`${API_URL}${API_PREFIX}/${joined}${req.nextUrl.search}`, {
      method: req.method,
      cache: "no-store",
      headers: {
        Authorization: `Bearer ${token}`,
        "Content-Type": "application/json",
        // One ID per request, shared with the API's log lines (and Sentry).
        "X-Request-ID": requestId,
      },
      body: req.method === "GET" ? undefined : await req.text(),
    });
  } catch {
    return NextResponse.json({ detail: "API not reachable" }, { status: 502 });
  }

  // Bytes, not text: a CSV export starts with a BOM that text decoding would drop.
  const body = await res.arrayBuffer();
  const headers: Record<string, string> = {
    "Content-Type": res.headers.get("Content-Type") ?? "application/json",
    "X-Request-ID": res.headers.get("X-Request-ID") ?? requestId,
  };
  // Downloads (CSV exports) keep their file name and are never cached.
  for (const name of ["Content-Disposition", "Cache-Control", "Retry-After"]) {
    const value = res.headers.get(name);
    if (value) headers[name] = value;
  }
  return new NextResponse(body, { status: res.status, headers });
}

export const GET = proxy;
export const POST = proxy;
export const PATCH = proxy;
