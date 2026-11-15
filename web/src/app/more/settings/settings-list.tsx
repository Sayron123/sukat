"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useEffect, useState, type ReactNode } from "react";

import { Icon } from "@/components/icons";
import { LogoutButton } from "@/components/logout-button";
import { Toast } from "@/components/toast";
import { Loading } from "@/components/ui";
import { api } from "@/lib/api-client";
import type { Me } from "@/lib/types";

import { ThemePicker } from "./theme-picker";

const VERSION = process.env.NEXT_PUBLIC_APP_VERSION;

function Group({ title, note, children }: { title: string; note?: string; children: ReactNode }) {
  return (
    <section>
      <h2 className="mb-2 text-[13px] font-bold text-muted uppercase">{title}</h2>
      {children}
      {note && <p className="mt-2 text-[13px] leading-snug text-subtle">{note}</p>}
    </section>
  );
}

function Rows({ children }: { children: ReactNode }) {
  return <ul className="divide-y divide-border rounded-card border border-border bg-surface">{children}</ul>;
}

function Row({ label, value, href, locked }: { label: string; value: string; href?: string; locked?: boolean }) {
  const body = (
    <>
      <span className="shrink-0 text-[15px] font-semibold text-text">{label}</span>
      <span className="min-w-0 flex-1 truncate text-right text-sm text-muted">{value}</span>
      {href && <Icon name="chevron" size={18} className="text-muted" />}
      {locked && (
        <>
          <Icon name="lock" size={16} className="text-muted" />
          <span className="sr-only">(can’t be changed)</span>
        </>
      )}
    </>
  );
  const cls = "flex min-h-14 items-center gap-3 px-4";
  return (
    <li>
      {href ? (
        <Link href={href} className={`${cls} hover:bg-background`}>
          {body}
        </Link>
      ) : (
        <div className={cls}>{body}</div>
      )}
    </li>
  );
}

function GoogleRow({ connected }: { connected: boolean }) {
  return (
    <li className="flex min-h-14 items-center gap-3 px-4">
      <span className="shrink-0 text-[15px] font-semibold text-text">Google</span>
      <span className="min-w-0 flex-1" />
      {connected ? (
        <span className="text-sm text-muted">Connected</span>
      ) : (
        <form method="post" action="/api/auth/google/start">
          <input type="hidden" name="mode" value="connect" />
          <button type="submit" className="min-h-11 text-sm font-bold text-accent-text underline">
            Connect
          </button>
        </form>
      )}
    </li>
  );
}

export function SettingsList() {
  const [me, setMe] = useState<Me | null | "error">(null);
  const [google, setGoogle] = useState(false);
  const problem = useSearchParams().get("error");

  useEffect(() => {
    api<Me>("auth/me").then(setMe, () => setMe("error"));
    api<{ client_id: string | null }>("auth/google").then((g) => setGoogle(g.client_id !== null), () => {});
  }, []);

  if (me === null) return <Loading />;
  if (me === "error") return <p className="text-sm text-red">Could not load your settings.</p>;

  const storeHref = me.role === "manager" ? "/more/settings/store" : undefined;

  return (
    <div className="flex flex-col gap-6">
      {problem && (
        <p role="alert" className="rounded-button border border-red-edge bg-red-soft p-3 text-sm text-red">
          {problem}
        </p>
      )}
      <Group
        title="Your account"
        note={`Your ${me.email ? "email" : "username"} is how you sign in. It can’t be changed here.`}
      >
        <Rows>
          <Row label="Name" value={me.full_name} href="/more/settings/name" />
          {me.email ? (
            <Row label="Email" value={me.email} locked />
          ) : (
            <Row label="Username" value={me.username ?? ""} locked />
          )}
          <Row label="Password" value="Change" href="/more/settings/password" />
          {(google || me.google) && <GoogleRow connected={me.google} />}
        </Rows>
      </Group>
      <Group title="Store" note={storeHref ? undefined : "Only a manager can change the store details."}>
        <Rows>
          <Row label="Store name" value={me.store_name} href={storeHref} />
          <Row label="Address" value={me.store_address || "Not set"} href={storeHref} />
        </Rows>
      </Group>
      <Group title="Appearance">
        <ThemePicker />
      </Group>
      <div className="mt-4 flex flex-col gap-4">
        <LogoutButton />
        {VERSION && <p className="text-center text-[13px] text-subtle">Sukat v{VERSION}</p>}
      </div>
      <Toast />
    </div>
  );
}
