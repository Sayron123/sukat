import type { Metadata } from "next";
import { headers } from "next/headers";
import Link from "next/link";
import { Suspense } from "react";

import { AuthForm, AuthShell } from "@/components/auth-form";
import { Loading, Notice, textLinkClass } from "@/components/ui";
import { backendFetch, clientIpHeaders, errorMessage } from "@/lib/server/backend";
import { googleClientId } from "@/lib/server/google";

export const metadata: Metadata = { title: "Join a store · Sukat", referrer: "same-origin" };

const INVALID = "This invite link is invalid or has expired. Ask your manager for a new one.";
const SERVER_DOWN = "The Sukat server is not responding. Please try again.";

type SearchParams = Promise<{
  token?: string | string[];
  existing?: string | string[];
  error?: string | string[];
}>;
type Preview = { store_name: string; role: string; name: string | null };

export default function InvitePage({ searchParams }: { searchParams: SearchParams }) {
  return (
    <Suspense fallback={<Loading />}>
      <InviteContent searchParams={searchParams} />
    </Suspense>
  );
}

function InviteProblem({ message }: { message: string }) {
  return (
    <AuthShell title="Can't open this invite" subtitle="The link could not be used." back="/signup">
      <Notice>{message}</Notice>
      <Link href="/login" className={`${textLinkClass} mt-3`}>
        Back to sign in
      </Link>
    </AuthShell>
  );
}

async function InviteContent({ searchParams }: { searchParams: SearchParams }) {
  const { token, existing, error } = await searchParams;
  if (typeof token !== "string" || !token) return <InviteProblem message={INVALID} />;

  const forwardedFor = (await headers()).get("x-forwarded-for");
  let res: Response;
  try {
    res = await backendFetch("/staff/invites/preview", {
      method: "POST",
      body: JSON.stringify({ token }),
      headers: clientIpHeaders(forwardedFor),
    });
  } catch {
    return <InviteProblem message={SERVER_DOWN} />;
  }
  if (res.status === 429) {
    return <InviteProblem message={errorMessage(await res.json().catch(() => null), INVALID)} />;
  }
  if (res.status === 400 || res.status === 422) return <InviteProblem message={INVALID} />;
  if (!res.ok) return <InviteProblem message={SERVER_DOWN} />;

  const invite = (await res.json()) as Preview;
  const existingAccount = existing === "1";
  const google = !existingAccount && (await googleClientId()) ? { mode: "invite" as const, token } : undefined;
  const link = `/invite?token=${encodeURIComponent(token)}`;
  const who = invite.name ? `${invite.name}, you` : "You";
  return (
    <AuthForm
      title={`Join ${invite.store_name}`}
      subtitle={`${who} are invited as a ${invite.role}. ${
        existingAccount ? "Sign in with your Sukat account to join." : "Make your account to join."
      }`}
      endpoint="/api/auth/accept-invite"
      submitLabel="Join Store"
      extra={{ token }}
      alert={typeof error === "string" ? error : undefined}
      google={google}
      agreement
      fields={
        existingAccount
          ? [
              { name: "login", label: "Email or username", autoComplete: "username" },
              { name: "password", label: "Password", type: "password", autoComplete: "current-password" },
            ]
          : [
              {
                name: "username",
                label: "Username",
                autoComplete: "username",
                minLength: 3,
                maxLength: 30,
                placeholder: "e.g. juan.dc",
                hint: "You sign in with this. Use 3 to 30 small letters, numbers, dots or underscores.",
              },
              { name: "full_name", label: "Your name", autoComplete: "name", maxLength: 120 },
              { name: "password", label: "Password", type: "new-password" },
            ]
      }
      altLink={
        existingAccount
          ? { text: "New to Sukat? Make an account instead", href: link }
          : { text: "Already have a Sukat account? Join with it", href: `${link}&existing=1` }
      }
    />
  );
}
