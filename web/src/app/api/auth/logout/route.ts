import { NextResponse, type NextRequest } from "next/server";

import { isSameOrigin } from "@/lib/server/auth-route";
import { SESSION_COOKIE, SESSION_COOKIE_OPTIONS } from "@/lib/server/backend";

export async function POST(req: NextRequest) {
  if (!isSameOrigin(req)) {
    return NextResponse.json({ error: "Bad origin" }, { status: 403 });
  }
  const response = NextResponse.json({ ok: true });
  // Cleared with the same flags it was set with ("__Host-" cookies must stay Secure).
  response.cookies.set(SESSION_COOKIE, "", { ...SESSION_COOKIE_OPTIONS, maxAge: 0 });
  return response;
}
