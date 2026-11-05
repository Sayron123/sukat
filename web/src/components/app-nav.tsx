import Link from "next/link";

import { LogoutButton } from "./logout-button";

/** Top bar for signed-in pages. Static, so it renders instantly. */
export function AppNav({ active }: { active: "stock" | "staff" }) {
  const link = (href: string, label: string, key: typeof active) => (
    <Link
      href={href}
      aria-current={active === key ? "page" : undefined}
      className={`flex h-11 items-center rounded-button px-3 text-sm font-medium ${
        active === key ? "bg-surface text-accent" : "text-muted hover:text-text"
      }`}
    >
      {label}
    </Link>
  );
  return (
    <header className="sticky top-0 z-10 border-b border-border bg-background">
      <nav className="mx-auto flex w-full max-w-2xl items-center gap-1 px-4 py-2">
        <span className="mr-2 font-semibold text-accent">Sukat</span>
        {link("/stock", "Stock", "stock")}
        {link("/staff", "Staff", "staff")}
        <span className="ml-auto">
          <LogoutButton />
        </span>
      </nav>
    </header>
  );
}
