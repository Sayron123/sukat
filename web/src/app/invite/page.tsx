import type { Metadata } from "next";
import { headers } from "next/headers";
import Link from "next/link";
import { Suspense } from "react";

import { AuthForm, AuthShell } from "@/components/auth-form";
import { Loading, Notice, textLinkClass } from "@/components/ui";
import { backendFetch, clientIpHeaders, errorMessage } from "@/lib/server/backend";

export const metadata: Metadata = { title: "Join a store · Sukat", referrer: "no-referrer" };

const INVALID = "This invite link is invalid or has expired. Ask your manager for a new one.";
const SERVER_DOWN = "The Sukat server is not responding. Please try again.";

type SearchParams = Promise<{ token?: string | string[] }>;
type Preview = { store_name: string; role: string; email: string; has_account: boolean };

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
  const { token } = await searchParams;
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
  const role = invite.role === "secretary" ? "a secretary" : "a member";
  const next = invite.has_account
    ? `${invite.email} already has a Sukat account, so enter its password to join.`
    : "Create your password to join.";
  return (
    <AuthForm
      title={`Join ${invite.store_name}`}
      subtitle={`You are invited as ${role}. ${next}`}
      endpoint="/api/auth/accept-invite"
      submitLabel="Join Store"
      extra={{ token }}
      agreement
      fields={
        invite.has_account
          ? [
              {
                name: "password",
                label: "Your Sukat password",
                type: "password",
                autoComplete: "current-password",
              },
            ]
          : [
              { name: "email", label: "Email", type: "email", autoComplete: "username", locked: invite.email },
              { name: "password", label: "Password", type: "new-password" },
            ]
      }
      altLink={invite.has_account ? { text: "Forgot your password?", href: "/forgot-password" } : undefined}
      footer={{ text: "Already have an account? Sign in", href: "/login" }}
    />
  );
}
