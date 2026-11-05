"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { Icon, type IconName } from "@/components/icons";
import { LogoutButton } from "@/components/logout-button";
import { PageHeader } from "@/components/page-header";
import { Avatar } from "@/components/ui";
import { api } from "@/lib/api-client";
import { canEditProducts, type Me } from "@/lib/types";

import { ApiStatus } from "../api-status";

type Item = { href: string; icon: IconName; title: string; detail: string; writersOnly?: boolean };

const ITEMS: Item[] = [
  { href: "/transactions", icon: "history", title: "History", detail: "Sales and stock movements" },
  { href: "/staff", icon: "users", title: "Staff", detail: "People and permissions" },
  { href: "/stock/new", icon: "plus", title: "Add product", detail: "Create a stock item", writersOnly: true },
  { href: "/stock/import", icon: "box", title: "Import starter items", detail: "Pick from a ready-made list", writersOnly: true },
];

/** More tab: who is signed in, links to the other screens, and Sign out. */
export function MoreMenu() {
  const [me, setMe] = useState<Me | null>(null);
  useEffect(() => {
    api<Me>("auth/me").then(setMe, () => {});
  }, []);

  const items = ITEMS.filter((i) => !i.writersOnly || canEditProducts(me?.role));

  return (
    <>
      <PageHeader eyebrow={me?.store_name ?? " "} title="More" />
      {me && (
        <div className="mb-3 flex items-center gap-3.5 border-b border-border pt-2 pb-6">
          <Avatar name={me.store_name} large />
          <div className="min-w-0">
            <b className="block truncate text-base text-text">{me.store_name}</b>
            <span className="mt-1 block truncate text-sm text-muted">
              {me.full_name} · <span className="capitalize">{me.role}</span>
            </span>
          </div>
        </div>
      )}
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
