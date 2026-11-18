import { NextResponse, type NextRequest } from "next/server";

import { isSameOrigin, setSessionCookie } from "@/lib/server/auth-route";
import { backendFetch, clientIpHeaders, errorMessage } from "@/lib/server/backend";
import { TICKET_COOKIE, TICKET_COOKIE_OPTIONS, unpackTicket } from "@/lib/server/google";

const TIMED_OUT = "Your Google sign-in timed out. Please continue with Google again.";

function text(value: unknown): string | undefined {
  return typeof value === "string" && value.trim() ? value.trim() : undefined;
}

export async function POST(req: NextRequest) {
  if (!isSameOrigin(req)) return NextResponse.json({ error: "Bad origin" }, { status: 403 });
  const ticket = unpackTicket(req.cookies.get(TICKET_COOKIE)?.value);
  if (!ticket) return NextResponse.json({ error: TIMED_OUT }, { status: 400 });
  const form = (await req.json().catch(() => null)) as Record<string, unknown> | null;
  if (!form) return NextResponse.json({ error: "Invalid request" }, { status: 400 });

  const body =
    ticket.mode === "signup"
      ? {
          ticket: ticket.ticket,
          full_name: text(form.full_name) ?? "",
          store_name: text(form.store_name) ?? "",
          store_address: text(form.store_address) ?? null,
          accept_terms: form.accept_terms === true,
        }
      : {
          ticket: ticket.ticket,
          token: ticket.invite,
          full_name: text(form.full_name) ?? null,
          accept_terms: form.accept_terms === true,
        };

  let res: Response;
  try {
    res = await backendFetch(ticket.mode === "signup" ? "/auth/google/signup" : "/staff/invites/accept-google", {
      method: "POST",
      body: JSON.stringify(body),
      headers: clientIpHeaders(req.headers.get("x-forwarded-for")),
    });
  } catch {
    return NextResponse.json({ error: "API not reachable" }, { status: 502 });
  }
  const data: unknown = await res.json().catch(() => null);
  if (!res.ok) {
    return NextResponse.json({ error: errorMessage(data, "Something went wrong") }, { status: res.status });
  }

  const response = NextResponse.json({ ok: true });
  setSessionCookie(response, (data as { access_token: string }).access_token);
  response.cookies.set(TICKET_COOKIE, "", { ...TICKET_COOKIE_OPTIONS, maxAge: 0 });
  return response;
}
