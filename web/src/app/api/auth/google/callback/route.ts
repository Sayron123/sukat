import { NextResponse, type NextRequest } from "next/server";

import { setSessionCookie } from "@/lib/server/auth-route";
import { backendFetch, clientIpHeaders, errorMessage, getToken } from "@/lib/server/backend";
import {
  CALLBACK_PATH,
  COOKIE_OPTIONS,
  GOOGLE_COOKIE,
  type GoogleTrip,
  backTo,
  sameText,
  siteOrigin,
  unpackTrip,
} from "@/lib/server/google";

const FAILED = "Google sign-in didn't work. Please try again.";

const API_PATH: Record<GoogleTrip["mode"], string> = {
  login: "/auth/google/login",
  signup: "/auth/google/signup",
  invite: "/staff/invites/accept-google",
  connect: "/auth/google/connect",
};

export async function GET(req: NextRequest) {
  const origin = siteOrigin(req);
  const trip = unpackTrip(req.cookies.get(GOOGLE_COOKIE)?.value);
  const params = req.nextUrl.searchParams;
  const code = params.get("code");
  const state = params.get("state") ?? "";

  function finish(path: string, error?: string, token?: string) {
    const target = new URL(path, origin);
    if (error) target.searchParams.set("error", error);
    const response = NextResponse.redirect(target, 303);
    response.cookies.set(GOOGLE_COOKIE, "", { ...COOKIE_OPTIONS, maxAge: 0 });
    if (token) setSessionCookie(response, token);
    return response;
  }

  if (!trip || !sameText(trip.state, state)) return finish("/login", FAILED);
  const back = backTo(trip);
  if (params.get("error") === "access_denied") return finish(back);
  if (!code) return finish(back, FAILED);

  const flow = {
    code,
    code_verifier: trip.verifier,
    redirect_uri: `${origin}${CALLBACK_PATH}`,
    nonce: trip.nonce,
  };
  const extra =
    trip.mode === "signup"
      ? { store_name: trip.storeName, store_address: trip.storeAddress ?? null, accept_terms: true }
      : trip.mode === "invite"
        ? { token: trip.invite, accept_terms: true }
        : {};

  let res: Response;
  try {
    res = await backendFetch(API_PATH[trip.mode], {
      method: "POST",
      body: JSON.stringify({ ...flow, ...extra }),
      headers: clientIpHeaders(req.headers.get("x-forwarded-for")),
      token: trip.mode === "connect" ? await getToken() : undefined,
    });
  } catch {
    return finish(back, "The Sukat server is not responding. Please try again.");
  }
  const data: unknown = await res.json().catch(() => null);
  if (!res.ok) return finish(back, errorMessage(data, FAILED));
  if (trip.mode === "connect") return finish("/more/settings");
  return finish("/", undefined, (data as { access_token: string }).access_token);
}
