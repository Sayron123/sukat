"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { Icon } from "@/components/icons";
import { Toast } from "@/components/toast";
import { Avatar, Badge, Card, Chip } from "@/components/ui";
import { ApiError, api } from "@/lib/api-client";
import { addDays, storeDate } from "@/lib/dates";
import type { Me, PendingInvite, Role, Staff } from "@/lib/types";

import { LinkDialog, type ShareLink } from "./link-dialog";

const FILTERS: { role: Role | null; label: string }[] = [
  { role: null, label: "All" },
  { role: "manager", label: "Managers" },
  { role: "secretary", label: "Secretaries" },
  { role: "member", label: "Members" },
];

const NONE: Record<Role, string> = {
  manager: "No managers.",
  secretary: "No secretaries yet.",
  member: "No members yet.",
};

const ROLE_LABEL: Record<Role, string> = { manager: "Manager", secretary: "Secretary", member: "Member" };

function inviteLabel(invite: { name: string | null; role: Role }): string {
  return invite.name ?? `${ROLE_LABEL[invite.role]} invite`;
}

function sentAgo(iso: string): string {
  const day = storeDate(new Date(iso));
  const today = storeDate();
  if (day === today) return "sent today";
  if (day === addDays(today, -1)) return "sent yesterday";
  const days = Math.round((Date.parse(today) - Date.parse(day)) / 86_400_000);
  return `sent ${days} days ago`;
}

export function StaffList({ staff, me, invites }: { staff: Staff[]; me: Me; invites: PendingInvite[] | null }) {
  const [role, setRole] = useState<Role | null>(null);
  const shown = role ? staff.filter((s) => s.role === role) : staff;
  const canOpen = me.role === "manager";

  return (
    <>
      <div className="-mx-5 mb-4 flex gap-2 overflow-x-auto px-5 [scrollbar-width:none]" role="group" aria-label="Role">
        {FILTERS.map((f) => (
          <Chip key={f.label} selected={role === f.role} onClick={() => setRole(f.role)}>
            {f.label}
          </Chip>
        ))}
      </div>
      {role && shown.length === 0 ? (
        <Card className="text-center text-muted">{NONE[role]}</Card>
      ) : (
        <ul className="overflow-hidden rounded-card border border-border bg-surface">
          {shown.map((s, i) => (
            <li key={s.member_id} className={i > 0 ? "border-t border-border" : ""}>
              <StaffRow s={s} me={me} canOpen={canOpen} />
            </li>
          ))}
        </ul>
      )}
      {canOpen && (
        <p className="mt-2 px-1 text-[13px] text-muted">Tap a person to change their role or remove them.</p>
      )}
      {invites !== null && invites.length > 0 && <PendingInvites invites={invites} me={me} />}
      {invites === null && me.role !== "member" && (
        <p className="mt-6 px-1 text-sm text-red">Could not load the invites not accepted yet.</p>
      )}
      <Toast />
    </>
  );
}

function StaffRow({ s, me, canOpen }: { s: Staff; me: Me; canOpen: boolean }) {
  const name = s.alias ?? s.full_name;
  const you = s.user_id === me.user_id;
  const detail = [s.alias && s.full_name, s.email ?? (s.username && `@${s.username}`)].filter(Boolean).join(" · ");
  const body = (
    <>
      <Avatar name={name} accent={s.is_owner} />
      <div className="min-w-0 flex-1">
        <b className="block truncate text-[15px] text-text">
          {name}
          {you && <span className="font-normal text-muted"> (you)</span>}
        </b>
        {detail && <small className="mt-0.5 block truncate text-[13px] text-muted">{detail}</small>}
      </div>
      <div className="flex shrink-0 flex-col items-end gap-1">
        {s.is_owner ? <Badge tone="accent">Owner</Badge> : <Badge>{ROLE_LABEL[s.role]}</Badge>}
        {!s.active && <Badge tone="red">Inactive</Badge>}
      </div>
    </>
  );
  const cls = "flex min-h-16 items-center gap-3 px-4 py-3";
  return canOpen ? (
    <Link href={`/staff/${s.member_id}`} className={`${cls} hover:bg-border/40`}>
      {body}
      <Icon name="chevron" size={18} className="shrink-0 text-muted" />
    </Link>
  ) : (
    <div className={cls}>{body}</div>
  );
}

function PendingInvites({ invites, me }: { invites: PendingInvite[]; me: Me }) {
  const router = useRouter();
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [link, setLink] = useState<ShareLink | null>(null);

  async function resend(invite: PendingInvite) {
    setBusy(invite.id);
    setError(null);
    try {
      const made = await api<{ name: string | null; role: Role; expires_at: string; token: string }>(
        `staff/invites/${invite.id}/renew`,
        { method: "POST" },
      );
      setLink({
        url: `${window.location.origin}/invite?token=${made.token}`,
        title: `New link for ${inviteLabel(made)}`,
        note: `Send it to them. They join as ${ROLE_LABEL[made.role]}. The old link no longer works.`,
        expiresAt: made.expires_at,
      });
      router.refresh();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not make a new link. Please try again.");
    } finally {
      setBusy(null);
    }
  }

  return (
    <section className="mt-6">
      <h2 className="mb-2 px-1 text-xs font-bold tracking-[0.06em] text-muted uppercase">Invites not accepted yet</h2>
      <ul className="overflow-hidden rounded-card border border-border bg-surface">
        {invites.map((invite, i) => {
          const canResend = me.role === "manager" || invite.role === "member";
          return (
            <li
              key={invite.id}
              className={`flex min-h-16 items-center gap-3 px-4 py-3 ${i > 0 ? "border-t border-border" : ""}`}
            >
              <span className="grid h-[42px] w-[42px] shrink-0 place-items-center rounded-full bg-background text-muted">
                <Icon name="mail" size={20} />
              </span>
              <div className="min-w-0 flex-1">
                <b className="block truncate text-[15px] text-text">{inviteLabel(invite)}</b>
                <small className="mt-0.5 block text-[13px] text-muted">
                  {ROLE_LABEL[invite.role]} · {sentAgo(invite.created_at)}
                </small>
              </div>
              {canResend && (
                <button
                  type="button"
                  disabled={busy !== null}
                  onClick={() => void resend(invite)}
                  className="min-h-11 shrink-0 px-1 text-sm font-bold text-accent-text underline disabled:opacity-45"
                >
                  {busy === invite.id ? "Making…" : "Resend"}
                </button>
              )}
            </li>
          );
        })}
      </ul>
      {error && (
        <p role="alert" className="mt-2 px-1 text-sm text-red">
          {error}
        </p>
      )}
      <LinkDialog link={link} onClose={() => setLink(null)} />
    </section>
  );
}
