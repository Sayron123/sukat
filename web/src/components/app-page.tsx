import { Suspense, type ReactNode } from "react";

import { AppNav, type NavKey } from "./app-nav";
import { RequireSession } from "./require-session";

/** Layout for signed-in pages: nav bar + session check + centered content column. */
export function AppPage({ active, children }: { active: NavKey; children: ReactNode }) {
  return (
    <>
      <AppNav active={active} />
      <main className="mx-auto w-full max-w-2xl flex-1 p-4">
        <Suspense fallback={<p className="text-muted">Loading…</p>}>
          <RequireSession>{children}</RequireSession>
        </Suspense>
      </main>
    </>
  );
}
