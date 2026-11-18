import { NextResponse, type NextRequest } from "next/server";

import { isSameOrigin } from "@/lib/server/auth-route";
import {
  AUTH_URL,
  CALLBACK_PATH,
  COOKIE_OPTIONS,
  GOOGLE_COOKIE,
  type GoogleMode,
  backTo,
  challenge,
  googleClientId,
  packTrip,
  random,
  siteOrigin,
} from "@/lib/server/google";

const MODES: GoogleMode[] = ["login", "signup", "invite", "connect"];

function text(form: FormData, name: string): string | undefined {
  const value = form.get(name);
  return typeof value === "string" && value.trim() ? value.trim() : undefined;
}

export async function POST(req: NextRequest) {
  const origin = siteOrigin(req);
  if (!isSameOrigin(req)) return NextResponse.json({ error: "Bad origin" }, { status: 403 });
  const form = await req.formData();
  const mode = text(form, "mode") as GoogleMode | undefined;
  if (!mode || !MODES.includes(mode)) return NextResponse.redirect(`${origin}/login`, 303);
  const trip = {
    mode,
    state: random(),
    verifier: random(48),
    nonce: random(),
    invite: text(form, "token"),
  };
  const back = new URL(backTo(trip), origin);

  const clientId = await googleClientId();
  if (!clientId) {
    back.searchParams.set("error", "Sign in with Google isn't set up yet.");
    return NextResponse.redirect(back, 303);
  }

  const google = new URL(AUTH_URL);
  google.search = new URLSearchParams({
    client_id: clientId,
    redirect_uri: `${origin}${CALLBACK_PATH}`,
    response_type: "code",
    scope: "openid email profile",
    state: trip.state,
    nonce: trip.nonce,
    code_challenge: challenge(trip.verifier),
    code_challenge_method: "S256",
    prompt: "select_account",
  }).toString();
  const response = NextResponse.redirect(google, 303);
  response.cookies.set(GOOGLE_COOKIE, packTrip(trip), COOKIE_OPTIONS);
  return response;
}
