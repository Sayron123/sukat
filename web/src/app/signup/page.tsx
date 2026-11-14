import type { Metadata } from "next";
import Link from "next/link";

import { AuthShell } from "@/components/auth-form";
import { Icon, type IconName } from "@/components/icons";

export const metadata: Metadata = { title: "Create an account · Sukat" };

const CHOICES: { href: string; icon: IconName; title: string; detail: string; note: string }[] = [
  {
    href: "/signup/manager",
    icon: "home",
    title: "Manager",
    detail: "I run the store. I’ll set it up and invite my staff.",
    note: "Takes about 2 minutes",
  },
  {
    href: "/signup/member",
    icon: "users",
    title: "Staff",
    detail: "I work at a store. I’ll join my manager’s store.",
    note: "You need an invite link from your manager",
  },
];

export default function SignupPage() {
  return (
    <AuthShell title="Create an account" subtitle="Which one are you?" back="/login" inlineSubmit>
      <div className="flex flex-col gap-3">
        {CHOICES.map((c) => (
          <Link
            key={c.href}
            href={c.href}
            className="flex items-center gap-3.5 rounded-[18px] border-[1.5px] border-border bg-surface p-4 text-text hover:bg-border/40"
          >
            <span className="grid h-12 w-12 shrink-0 place-items-center rounded-[14px] border border-border bg-background">
              <Icon name={c.icon} size={24} />
            </span>
            <span className="flex min-w-0 flex-1 flex-col gap-1">
              <b className="text-[17px] font-extrabold">{c.title}</b>
              <span className="text-sm leading-5 text-muted">{c.detail}</span>
              <span className="text-[13px] leading-[18px] font-semibold">{c.note}</span>
            </span>
            <Icon name="chevron" size={22} className="text-muted" />
          </Link>
        ))}
      </div>
      <Link
        href="/login"
        className="mt-auto inline-flex min-h-11 items-center self-center pt-8 text-[15px] font-semibold text-accent-text underline"
      >
        Already have an account? Sign in
      </Link>
    </AuthShell>
  );
}
