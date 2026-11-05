import type { ReactNode } from "react";

/**
 * Bar fixed to the bottom of the screen for the screen's main button. Sits above the
 * bottom tabs when the page has them (AppPage sets --nav-h).
 */
export function ActionDock({ children }: { children: ReactNode }) {
  return (
    <div className="fixed inset-x-0 bottom-[var(--nav-h,0px)] z-10 bg-background">
      <div className="mx-auto flex max-w-lg flex-col gap-2 px-5 pt-3 pb-4">{children}</div>
    </div>
  );
}
