import Link from "next/link";

import { Icon, type IconName } from "./icons";

/** The main tabs. Pages without a tab (forms, scan, staff, history) show a back arrow instead. */
export type Tab = "home" | "stock" | "ai" | "more";

const TABS: { key: Tab; label: string; icon: IconName; href?: string }[] = [
  { key: "home", label: "Home", icon: "home", href: "/" },
  { key: "stock", label: "Stock", icon: "box", href: "/stock" },
  { key: "ai", label: "Ask Sukat", icon: "sukat", href: "/ai" },
  { key: "more", label: "More", icon: "menu", href: "/more" },
];

/** Bottom tab bar (68px). Static, so it renders instantly. */
export function BottomNav({ active }: { active: Tab }) {
  return (
    <nav aria-label="Main" className="fixed inset-x-0 bottom-0 z-20 border-t border-border bg-background">
      <div className="mx-auto grid h-[68px] max-w-lg grid-cols-4 pb-1">
        {TABS.map((t) => {
          const body = (
            <>
              {active === t.key && (
                <span aria-hidden className="absolute top-0 left-1/2 h-1 w-8 -translate-x-1/2 rounded-b-full bg-accent" />
              )}
              <Icon name={t.icon} size={23} />
              <span className={active === t.key ? "font-extrabold" : ""}>{t.label}</span>
            </>
          );
          const cls = "relative flex flex-col items-center justify-center gap-[3px] text-xs font-semibold";
          return t.href ? (
            <Link
              key={t.key}
              href={t.href}
              aria-current={active === t.key ? "page" : undefined}
              className={`${cls} ${active === t.key ? "text-text" : "text-subtle hover:text-text"}`}
            >
              {body}
            </Link>
          ) : (
            <span key={t.key} aria-disabled title="Coming soon" className={`${cls} text-subtle opacity-50`}>
              {body}
            </span>
          );
        })}
      </div>
    </nav>
  );
}
