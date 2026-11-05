import { NextResponse, type NextRequest } from "next/server";

import { isSameOrigin } from "@/lib/server/auth-route";
import { API_URL, getToken } from "@/lib/server/backend";

/**
 * Same-origin proxy from the browser to the FastAPI backend.
 *
 * The access token lives in an httpOnly cookie that browser code cannot read, so
 * client components call /api/backend/<path> and this handler adds the token.
 * Only the API areas the web app uses are allowed through.
 */
const ALLOWED_PREFIXES = ["products", "catalog", "auth/me"];

async function proxy(req: NextRequest, ctx: RouteContext<"/api/backend/[...path]">) {
  const { path } = await ctx.params;
  const joined = path.join("/");
  if (!ALLOWED_PREFIXES.some((p) => joined === p || joined.startsWith(`${p}/`))) {
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

  let res: Response;
  try {
    res = await fetch(`${API_URL}/${joined}${req.nextUrl.search}`, {
      method: req.method,
      cache: "no-store",
      headers: {
        Authorization: `Bearer ${token}`,
        "Content-Type": "application/json",
      },
      body: req.method === "GET" ? undefined : await req.text(),
    });
  } catch {
    return NextResponse.json({ detail: "API not reachable" }, { status: 502 });
  }

  const body = await res.text();
  return new NextResponse(body, {
    status: res.status,
    headers: { "Content-Type": res.headers.get("Content-Type") ?? "application/json" },
  });
}

export const GET = proxy;
export const POST = proxy;
export const PATCH = proxy;
