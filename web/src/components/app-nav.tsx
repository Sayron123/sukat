import Link from "next/link";

import { LogoutButton } from "./logout-button";

/** Top bar for signed-in pages. Static, so it renders instantly. */
export type NavKey = "stock" | "scan" | "history" | "staff";

export function AppNav({ active }: { active: NavKey }) {
  const link = (href: string, label: string, key: typeof active) => (
    <Link
      href={href}
      aria-current={active === key ? "page" : undefined}
      className={`flex h-11 items-center rounded-button px-2 text-sm font-medium sm:px-3 ${
        active === key ? "bg-surface text-accent" : "text-muted hover:text-text"
      }`}
    >
      {label}
    </Link>
  );
  return (
    <header className="sticky top-0 z-10 border-b border-border bg-background">
      <nav className="mx-auto flex w-full max-w-2xl items-center gap-1 px-4 py-2">
        {/* Hidden on the narrowest phones so the four links and Log out fit in one row. */}
        <span className="mr-1 hidden font-semibold text-accent min-[380px]:inline">Sukat</span>
        {link("/stock", "Stock", "stock")}
        {link("/scan", "Scan", "scan")}
        {link("/transactions", "History", "history")}
        {link("/staff", "Staff", "staff")}
        <span className="ml-auto">
          <LogoutButton />
        </span>
      </nav>
    </header>
  );
}
