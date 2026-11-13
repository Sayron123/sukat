"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { Icon, type IconName } from "@/components/icons";
import { LogoutButton } from "@/components/logout-button";
import { PageHeader, headerIconClass } from "@/components/page-header";
import { Avatar, Notice, textLinkClass } from "@/components/ui";
import { ApiError, api } from "@/lib/api-client";
import { canEditProducts, type Me, type Role, type Staff } from "@/lib/types";

import { ApiStatus } from "../api-status";

type Item = {
  href: string;
  icon: IconName;
  title: string;
  detail: string;
  writersOnly?: boolean;
  managersOnly?: boolean;
};

type Group = { title?: string; items: Item[] };

const ROLE_SHORT: Record<Role, string> = { manager: "Mgr", secretary: "Sec", member: "Mem" };

const GROUPS: Group[] = [
  {
    title: "Store",
    items: [
      { href: "/transactions", icon: "history", title: "History", detail: "Sales and stock movements" },
      { href: "/more/export", icon: "download", title: "Download store data", detail: "Products, history and stock as CSV", managersOnly: true },
      { href: "/more/ai-usage", icon: "sukat", title: "AI usage", detail: "This month's spending and limit", managersOnly: true },
    ],
  },
  {
    title: "Products",
    items: [
      { href: "/stock/new", icon: "plus", title: "Add product", detail: "Create a stock item", writersOnly: true },
      { href: "/stock/import", icon: "box", title: "Import starter items", detail: "Pick from a ready-made list", writersOnly: true },
    ],
  },
  {
    title: "People",
    items: [
      { href: "/staff", icon: "users", title: "Staff", detail: "People and permissions" },
      { href: "/attendance", icon: "calendar", title: "Attendance", detail: "Mark who came in each day", writersOnly: true },
    ],
  },
  {
    items: [{ href: "/privacy", icon: "check", title: "Privacy and terms", detail: "What we store and why" }],
  },
];

function VerifyEmailNotice({ email }: { email: string }) {
  const [status, setStatus] = useState<string | null>(null);

  async function resend() {
    try {
      await api("auth/resend-verification", { method: "POST" });
      setStatus(`Link sent to ${email}.`);
    } catch (e) {
      setStatus(e instanceof ApiError ? e.message : "Could not send the link.");
    }
  }

  return (
    <Notice title="Confirm your email" className="mt-6">
      Photo reading and the AI assistant unlock after you confirm.
      {status ? (
        <p className="mt-1">{status}</p>
      ) : (
        <button type="button" onClick={resend} className={`${textLinkClass} block`}>
          Resend the link
        </button>
      )}
    </Notice>
  );
}

/** More tab: who is signed in, links to the other screens, and Sign out. */
export function MoreMenu() {
  const [me, setMe] = useState<Me | null>(null);
  const [staffCount, setStaffCount] = useState<number | null>(null);
  useEffect(() => {
    api<Me>("auth/me").then(setMe, () => {});
    api<Staff[]>("staff").then((s) => setStaffCount(s.length), () => {});
  }, []);

  const groups = GROUPS.map((g) => ({
    ...g,
    items: g.items.filter(
      (i) => (!i.writersOnly || canEditProducts(me?.role)) && (!i.managersOnly || me?.role === "manager"),
    ),
  })).filter((g) => g.items.length > 0);

  function detailFor(i: Item) {
    if (i.href === "/staff" && staffCount !== null) return `${staffCount} ${staffCount === 1 ? "person" : "people"}`;
    return i.detail;
  }

  return (
    <>
      <PageHeader eyebrow={me?.store_name ?? " "} title="More" />
      {me && (
        <div className="flex items-center gap-3.5 border-b border-border pt-2 pb-6">
          <Avatar name={me.full_name} large text={ROLE_SHORT[me.role]} />
          <div className="min-w-0 flex-1">
            <b className="block truncate text-base text-text">{me.full_name}</b>
            <span className="mt-1 block truncate text-sm text-muted capitalize">{me.role}</span>
          </div>
          <Link href="/more/settings" aria-label="Settings" title="Settings" className={headerIconClass}>
            <Icon name="settings" />
          </Link>
        </div>
      )}
      {me && !me.email_verified && <VerifyEmailNotice email={me.email} />}
      {groups.map((g) => (
        <section key={g.title ?? g.items[0].href} className="mt-8">
          {g.title && <h2 className="mb-2 text-[13px] font-bold text-muted uppercase">{g.title}</h2>}
          <ul className="border-t border-border">
            {g.items.map((i) => (
              <li key={i.href}>
                <Link href={i.href} className="flex min-h-[72px] items-center gap-3 border-b border-border text-text">
                  <span className="grid h-10 w-10 shrink-0 place-items-center">
                    <Icon name={i.icon} size={21} />
                  </span>
                  <span className="min-w-0 flex-1">
                    <b className="block text-base">{i.title}</b>
                    <small className="mt-1 block text-sm text-muted">{detailFor(i)}</small>
                  </span>
                  <Icon name="chevron" size={19} />
                </Link>
              </li>
            ))}
          </ul>
        </section>
      ))}
      <div className="mt-6">
        <LogoutButton />
      </div>
      <div className="mt-6 text-sm text-muted">
        <ApiStatus />
      </div>
    </>
  );
}
