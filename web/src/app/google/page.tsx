import type { Metadata } from "next";
import { cookies, headers } from "next/headers";
import { redirect } from "next/navigation";
import { Suspense } from "react";

import { AuthForm } from "@/components/auth-form";
import { Loading } from "@/components/ui";
import { backendFetch, clientIpHeaders } from "@/lib/server/backend";
import { TICKET_COOKIE, unpackTicket } from "@/lib/server/google";

export const metadata: Metadata = { title: "Almost done · Sukat" };

const TIMED_OUT = "Your Google sign-in timed out. Please continue with Google again.";

type Preview = { store_name: string; role: string };

export default function GoogleFinishPage() {
  return (
    <Suspense fallback={<Loading />}>
      <GoogleFinish />
    </Suspense>
  );
}

async function invitePreview(token: string): Promise<Preview | null> {
  try {
    const res = await backendFetch("/staff/invites/preview", {
      method: "POST",
      body: JSON.stringify({ token }),
      headers: clientIpHeaders((await headers()).get("x-forwarded-for")),
    });
    return res.ok ? ((await res.json()) as Preview) : null;
  } catch {
    return null;
  }
}

async function GoogleFinish() {
  const ticket = unpackTicket((await cookies()).get(TICKET_COOKIE)?.value);
  if (!ticket) redirect(`/login?error=${encodeURIComponent(TIMED_OUT)}`);
  const nameField = {
    name: "full_name",
    label: "Your name",
    autoComplete: "name",
    maxLength: 120,
    defaultValue: ticket.name,
    hint: "From your Google account. You can change it.",
  };

  if (ticket.mode === "signup") {
    return (
      <AuthForm
        title="Set up your store"
        subtitle={`Signed in with Google as ${ticket.email}.`}
        mascot={104}
        endpoint="/api/auth/google/finish"
        submitLabel="Create store"
        back="/signup/manager"
        agreement
        fields={[
          {
            name: "store_name",
            label: "Store name",
            autoComplete: "organization",
            placeholder: "Hardware (Branch)",
            section: "Your store",
          },
          {
            name: "store_address",
            label: "Store address (optional)",
            autoComplete: "street-address",
            maxLength: 300,
            optional: true,
            section: "Your store",
          },
          { ...nameField, section: "You" },
        ]}
      />
    );
  }

  const invite = await invitePreview(ticket.invite ?? "");
  const back = `/invite?token=${encodeURIComponent(ticket.invite ?? "")}`;
  if (!invite) redirect(back);
  return (
    <AuthForm
      title={`Join ${invite.store_name}`}
      subtitle={`You are invited as a ${invite.role}. Signed in with Google as ${ticket.email}.`}
      endpoint="/api/auth/google/finish"
      submitLabel="Join Store"
      back={back}
      agreement
      fields={ticket.account ? [] : [nameField]}
    />
  );
}
