"use client";

import { useState, type FormEvent } from "react";

import { Button, Card, Field, GhostButton } from "@/components/ui";
import { ApiError, api } from "@/lib/api-client";

const ROLES = [
  { value: "secretary", title: "Secretary", detail: "Can edit products and void sales" },
  { value: "member", title: "Member", detail: "Can scan sales and stock" },
];

type Invite = { email: string; role: string; expires_at: string; token: string };
type Created = { link: string; email: string; role: string; expires: string };

export function InviteForm() {
  const [created, setCreated] = useState<Created | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);
  const [copyNote, setCopyNote] = useState<string | null>(null);

  async function onSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const { email, role } = Object.fromEntries(new FormData(e.currentTarget));
    setError(null);
    setPending(true);
    try {
      const invite = await api<Invite>("staff/invites", {
        method: "POST",
        body: JSON.stringify({ email, role }),
      });
      setCopyNote(null);
      setCreated({
        link: `${window.location.origin}/invite?token=${invite.token}`,
        email: invite.email,
        role: invite.role,
        expires: new Date(invite.expires_at).toLocaleDateString("en-PH", { month: "long", day: "numeric" }),
      });
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not create the link.");
    } finally {
      setPending(false);
    }
  }

  async function copy(link: string) {
    try {
      await navigator.clipboard.writeText(link);
      setCopyNote("Link copied.");
    } catch {
      setCopyNote("Press and hold the link above to copy it.");
    }
  }

  if (created) {
    const canShare = typeof navigator.share === "function";
    return (
      <Card className="mb-4 flex flex-col gap-3">
        <div>
          <b className="block text-base text-text">Send this link</b>
          <p className="mt-1 text-sm text-muted">
            {created.email} will join as a <span className="capitalize">{created.role}</span>. It works once, until{" "}
            {created.expires}.
          </p>
        </div>
        <Field id="invite-link" label="Invite link" readOnly value={created.link} onFocus={(e) => e.target.select()} />
        <div className="flex gap-2">
          <Button type="button" onClick={() => copy(created.link)}>
            Copy link
          </Button>
          {canShare && (
            <GhostButton
              type="button"
              className="w-full"
              onClick={() => navigator.share({ title: "Join on Sukat", url: created.link }).catch(() => {})}
            >
              Share
            </GhostButton>
          )}
        </div>
        {copyNote && (
          <p role="status" className="text-[13px] text-muted">
            {copyNote}
          </p>
        )}
        <GhostButton type="button" onClick={() => setCreated(null)}>
          Invite someone else
        </GhostButton>
      </Card>
    );
  }

  return (
    <Card className="mb-4">
      <form onSubmit={onSubmit} className="flex flex-col gap-4">
        <b className="block text-base text-text">Invite someone</b>
        <Field id="invite-email" name="email" type="email" label="Their email" autoComplete="off" required />
        <fieldset className="flex flex-col gap-2">
          <legend className="mb-[7px] text-[13px] font-bold text-text">What will they be?</legend>
          {ROLES.map((r) => (
            <label
              key={r.value}
              className="flex min-h-[64px] cursor-pointer items-center gap-3 rounded-button border border-line px-3 has-checked:border-text has-checked:bg-surface"
            >
              <input type="radio" name="role" value={r.value} required className="h-5 w-5 accent-accent" />
              <span className="min-w-0">
                <b className="block text-[15px] text-text">{r.title}</b>
                <small className="block text-[13px] text-muted">{r.detail}</small>
              </span>
            </label>
          ))}
        </fieldset>
        {error && (
          <p role="alert" className="text-sm text-red">
            {error}
          </p>
        )}
        <Button type="submit" disabled={pending}>
          {pending ? "Please wait…" : "Create invite link"}
        </Button>
      </form>
    </Card>
  );
}
