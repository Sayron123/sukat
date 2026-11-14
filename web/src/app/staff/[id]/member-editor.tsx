"use client";

import { useRouter } from "next/navigation";
import { useEffect, useRef, useState, type FormEvent } from "react";

import { ActionDock } from "@/components/action-dock";
import { Icon } from "@/components/icons";
import { Mascot } from "@/components/mascot";
import { showToast } from "@/components/toast";
import { Button, Field, GhostButton, Notice } from "@/components/ui";
import { ApiError, api } from "@/lib/api-client";
import type { Role, Staff } from "@/lib/types";

import { LinkDialog, type ShareLink } from "../link-dialog";

const ROLES: { value: Role; title: string; detail: string }[] = [
  { value: "manager", title: "Manager", detail: "Everything a secretary can do, plus manage staff and store settings." },
  { value: "secretary", title: "Secretary", detail: "Add and edit products, fix stock, and void sales." },
  { value: "member", title: "Member", detail: "Scan sales and stock received. Can’t change products." },
];

const FORM = "member-form";

export function MemberEditor({
  member,
  storeName,
  canChange,
  canRename,
}: {
  member: Staff;
  storeName: string;
  canChange: boolean;
  canRename: boolean;
}) {
  const router = useRouter();
  const name = member.alias ?? member.full_name;
  const [role, setRole] = useState<Role>(member.role);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [removing, setRemoving] = useState(false);
  const [resetLink, setResetLink] = useState<ShareLink | null>(null);

  async function onSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const alias = String(new FormData(e.currentTarget).get("alias") ?? "").trim();
    const roleChanged = canChange && role !== member.role;
    const aliasChanged = canRename && alias !== (member.alias ?? "");
    if (!roleChanged && !aliasChanged) {
      router.push("/staff");
      return;
    }
    setError(null);
    setPending(true);
    try {
      if (roleChanged) {
        await api(`staff/${member.member_id}/role`, { method: "PATCH", body: JSON.stringify({ role }) });
      }
      if (aliasChanged) {
        await api(`staff/${member.member_id}/alias`, { method: "PATCH", body: JSON.stringify({ alias }) });
      }
      showToast(`${alias || member.full_name} saved`);
      router.push("/staff");
      router.refresh();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not save. Please try again.");
      setPending(false);
    }
  }

  async function makeResetLink() {
    setPending(true);
    setError(null);
    try {
      const made = await api<{ token: string; expires_at: string }>(`staff/${member.member_id}/reset-link`, {
        method: "POST",
      });
      setResetLink({
        url: `${window.location.origin}/reset-password?token=${made.token}`,
        title: `Password reset link for ${name}`,
        note: "Give it only to them. They open it to set a new password.",
        expiresAt: made.expires_at,
      });
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not make the link. Please try again.");
    } finally {
      setPending(false);
    }
  }

  async function remove() {
    setPending(true);
    setError(null);
    try {
      await api(`staff/${member.member_id}/deactivate`, { method: "POST" });
      showToast(`${name} was removed`);
      router.push("/staff");
      router.refresh();
    } catch (err) {
      setRemoving(false);
      setError(err instanceof ApiError ? err.message : "Could not remove them. Please try again.");
      setPending(false);
    }
  }

  return (
    <>
      <form id={FORM} onSubmit={onSubmit} className="flex flex-col gap-6">
        {!member.active && (
          <Notice icon="users" title="Removed from the store">
            They can’t sign in to {storeName}. Invite them again to bring them back.
          </Notice>
        )}
        <section>
          <h2 className="mb-2 px-1 text-xs font-bold tracking-[0.06em] text-muted uppercase">Role</h2>
          {canChange ? (
            <fieldset className="flex flex-col gap-2">
              <legend className="sr-only">Role</legend>
              {ROLES.map((r) => {
                const on = role === r.value;
                return (
                  <label
                    key={r.value}
                    className={`flex cursor-pointer items-start gap-3 rounded-card border bg-surface p-4 ${
                      on ? "border-text ring-1 ring-text" : "border-border"
                    }`}
                  >
                    <input
                      type="radio"
                      name="role"
                      value={r.value}
                      checked={on}
                      onChange={() => setRole(r.value)}
                      className="mt-0.5 h-5 w-5 shrink-0 accent-accent"
                    />
                    <span className="min-w-0">
                      <b className="block text-[15px] text-text">
                        {r.title}
                        {member.role === r.value && <span className="font-normal text-muted"> · current</span>}
                      </b>
                      <span className="mt-0.5 block text-[13px] leading-snug text-muted">{r.detail}</span>
                    </span>
                  </label>
                );
              })}
            </fieldset>
          ) : (
            <p className="rounded-card border border-border bg-surface p-4 text-[15px] text-text">
              {member.is_owner ? "Owner" : ROLES.find((r) => r.value === member.role)?.title}
              <span className="mt-0.5 block text-[13px] text-muted">
                {member.is_owner
                  ? "The store owner’s role can’t be changed."
                  : member.active
                    ? "You can’t change your own role."
                    : "Invite them again to give them a role."}
              </span>
            </p>
          )}
        </section>
        {canRename && (
          <section>
            <h2 className="mb-2 px-1 text-xs font-bold tracking-[0.06em] text-muted uppercase">Name in this store</h2>
            <Field
              id="alias"
              name="alias"
              label="Name or alias"
              defaultValue={member.alias ?? ""}
              placeholder={member.full_name}
              maxLength={120}
              autoComplete="off"
              hint="Leave empty to use their account name."
            />
          </section>
        )}
        {canChange && (
          <section>
            <h2 className="mb-2 px-1 text-xs font-bold tracking-[0.06em] text-muted uppercase">Password</h2>
            <button
              type="button"
              disabled={pending}
              onClick={() => void makeResetLink()}
              className="flex min-h-14 w-full items-center gap-3 rounded-card border border-border bg-surface px-4 py-3 text-left hover:bg-border/40 disabled:opacity-45"
            >
              <Icon name="lock" size={20} className="shrink-0 text-muted" />
              <span className="min-w-0 flex-1">
                <b className="block text-[15px] text-text">Make a password reset link</b>
                <small className="mt-0.5 block text-[13px] text-muted">For when they forgot their password</small>
              </span>
              <Icon name="chevron" size={18} className="shrink-0 text-muted" />
            </button>
          </section>
        )}
        {canChange && (
          <button
            type="button"
            onClick={() => setRemoving(true)}
            className="flex h-12 w-full items-center justify-center gap-2 rounded-button border border-line bg-surface px-4 text-[15px] font-semibold text-red hover:bg-red-soft"
          >
            <Icon name="trash" size={20} />
            Remove from store
          </button>
        )}
      </form>

      {(canChange || canRename) && (
        <ActionDock>
          {error && (
            <p role="alert" className="text-sm text-red">
              {error}
            </p>
          )}
          <Button type="submit" form={FORM} size="lg" disabled={pending}>
            {pending ? "Saving…" : canChange ? "Save role" : "Save name"}
          </Button>
        </ActionDock>
      )}

      <LinkDialog link={resetLink} onClose={() => setResetLink(null)} />
      <RemoveSheet
        open={removing}
        name={name}
        storeName={storeName}
        busy={pending}
        onConfirm={() => void remove()}
        onCancel={() => setRemoving(false)}
      />
    </>
  );
}

function RemoveSheet({
  open,
  name,
  storeName,
  busy,
  onConfirm,
  onCancel,
}: {
  open: boolean;
  name: string;
  storeName: string;
  busy: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const dialog = ref.current;
    if (!dialog) return;
    if (open && !dialog.open) dialog.showModal();
    if (!open && dialog.open) dialog.close();
  }, [open]);

  return (
    <dialog
      ref={ref}
      aria-labelledby="remove-title"
      onCancel={(e) => {
        e.preventDefault();
        onCancel();
      }}
      className="mx-auto mt-auto mb-0 w-full max-w-lg rounded-t-card bg-background text-text backdrop:bg-dark/40"
    >
      <div className="flex flex-col items-center gap-3 p-5 pb-[max(20px,env(safe-area-inset-bottom))] text-center">
        <span aria-hidden className="h-1.5 w-10 rounded-full bg-border" />
        <Mascot emote="warning" size={72} alt="" />
        <h2 id="remove-title" className="text-lg font-bold">
          Remove {name}?
        </h2>
        <p className="text-sm text-muted">
          They won’t be able to sign in to {storeName} anymore. Their past sales and scans stay in your records.
        </p>
        <p className="text-[13px] text-subtle">You can invite them again later.</p>
        <div className="mt-2 flex w-full flex-col gap-2">
          <Button type="button" size="lg" variant="danger" disabled={busy} onClick={onConfirm}>
            {busy ? "Removing…" : `Remove ${name}`}
          </Button>
          <GhostButton type="button" disabled={busy} onClick={onCancel}>
            Cancel
          </GhostButton>
        </div>
      </div>
    </dialog>
  );
}
