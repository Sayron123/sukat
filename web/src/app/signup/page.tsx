import type { Metadata } from "next";
import Link from "next/link";

import { AuthShell } from "@/components/auth-form";
import { Icon, type IconName } from "@/components/icons";
import { textLinkClass } from "@/components/ui";

export const metadata: Metadata = { title: "Create an account · Sukat" };

const CHOICES: { href: string; icon: IconName; title: string; detail: string }[] = [
  {
    href: "/signup/manager",
    icon: "home",
    title: "Manager",
    detail: "I run the store. Set it up and invite my staff.",
  },
  {
    href: "/signup/member",
    icon: "users",
    title: "Member",
    detail: "I work at a store. Join with my manager's invite link.",
  },
];

export default function SignupPage() {
  return (
    <AuthShell title="Create an account" subtitle="Which one are you?" back="/login">
      <div className="flex flex-col gap-3">
        {CHOICES.map((c) => (
          <Link
            key={c.href}
            href={c.href}
            className="flex min-h-[84px] items-center gap-3 rounded-card border border-border bg-surface px-4 text-text hover:bg-border/40"
          >
            <Icon name={c.icon} size={22} />
            <span className="min-w-0 flex-1">
              <b className="block text-base">{c.title}</b>
              <small className="mt-1 block text-sm leading-snug text-muted">{c.detail}</small>
            </span>
            <Icon name="chevron" size={19} />
          </Link>
        ))}
      </div>
      <Link href="/login" className={`${textLinkClass} mt-3`}>
        Already have an account? Sign in
      </Link>
    </AuthShell>
  );
}
