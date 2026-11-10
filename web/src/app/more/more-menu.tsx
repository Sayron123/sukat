"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { Icon, type IconName } from "@/components/icons";
import { LogoutButton } from "@/components/logout-button";
import { PageHeader, headerIconClass } from "@/components/page-header";
import { Avatar, Notice, textLinkClass } from "@/components/ui";
import { ApiError, api } from "@/lib/api-client";
import { canEditProducts, type Me } from "@/lib/types";

import { ApiStatus } from "../api-status";

type Item = {
  href: string;
  icon: IconName;
  title: string;
  detail: string;
  writersOnly?: boolean;
  managersOnly?: boolean;
};

const ITEMS: Item[] = [
  { href: "/transactions", icon: "history", title: "History", detail: "Sales and stock movements" },
  { href: "/staff", icon: "users", title: "Staff", detail: "People and permissions" },
  { href: "/more/ai-usage", icon: "spark", title: "AI usage", detail: "This month's spending and limit", managersOnly: true },
  { href: "/stock/new", icon: "plus", title: "Add product", detail: "Create a stock item", writersOnly: true },
  { href: "/stock/import", icon: "box", title: "Import starter items", detail: "Pick from a ready-made list", writersOnly: true },
  { href: "/more/export", icon: "download", title: "Download store data", detail: "Products, history and stock as CSV", managersOnly: true },
  { href: "/privacy", icon: "check", title: "Privacy and terms", detail: "What we store and why" },
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
    <Notice title="Confirm your email" className="mb-4">
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
  useEffect(() => {
    api<Me>("auth/me").then(setMe, () => {});
  }, []);

  const items = ITEMS.filter(
    (i) => (!i.writersOnly || canEditProducts(me?.role)) && (!i.managersOnly || me?.role === "manager"),
  );

  return (
    <>
      <PageHeader eyebrow={me?.store_name ?? " "} title="More" />
      {me && (
        <div className="mb-3 flex items-center gap-3.5 border-b border-border pt-2 pb-6">
          <Avatar name={me.store_name} large />
          <div className="min-w-0 flex-1">
            <b className="block truncate text-base text-text">{me.store_name}</b>
            {me.store_address && (
              <span className="mt-1 block truncate text-sm text-muted">{me.store_address}</span>
            )}
            <span className="mt-1 block truncate text-sm text-muted">
              {me.full_name} · <span className="capitalize">{me.role}</span>
            </span>
          </div>
          <Link href="/more/settings" aria-label="Settings" title="Settings" className={headerIconClass}>
            <Icon name="settings" />
          </Link>
        </div>
      )}
      {me && !me.email_verified && <VerifyEmailNotice email={me.email} />}
      <ul className="border-t border-border">
        {items.map((i) => (
          <li key={i.href}>
            <Link href={i.href} className="flex min-h-[72px] items-center gap-3 border-b border-border text-text">
              <span className="grid h-10 w-8 place-items-center">
                <Icon name={i.icon} size={21} />
              </span>
              <span className="min-w-0 flex-1">
                <b className="block text-base">{i.title}</b>
                <small className="mt-1 block text-sm text-muted">{i.detail}</small>
              </span>
              <Icon name="chevron" size={19} />
            </Link>
          </li>
        ))}
      </ul>
      <div className="mt-6">
        <LogoutButton />
      </div>
      <div className="mt-6 text-sm text-muted">
        <ApiStatus />
      </div>
    </>
  );
}
