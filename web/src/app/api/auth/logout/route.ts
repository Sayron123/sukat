import { NextResponse, type NextRequest } from "next/server";

import { isSameOrigin } from "@/lib/server/auth-route";
import { SESSION_COOKIE, SESSION_COOKIE_OPTIONS, backendFetch, getToken } from "@/lib/server/backend";

export async function POST(req: NextRequest) {
  if (!isSameOrigin(req)) {
    return NextResponse.json({ error: "Bad origin" }, { status: 403 });
  }
  const token = await getToken();
  if (token) await backendFetch("/auth/logout", { method: "POST", token }).catch(() => null);
  const response = NextResponse.json({ ok: true });
  response.cookies.set(SESSION_COOKIE, "", { ...SESSION_COOKIE_OPTIONS, maxAge: 0 });
  return response;
}
