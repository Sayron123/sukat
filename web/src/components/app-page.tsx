import { Suspense, type CSSProperties, type ReactNode } from "react";

import { BottomNav, type Tab } from "./app-nav";
import { RequireSession } from "./require-session";
import { Loading } from "./ui";

/**
 * Layout for signed-in pages: session check + centered phone-width column. Pass `tab` on
 * the main screens to show the bottom tab bar. Bottom padding leaves room for the bars.
 */
export function AppPage({ tab, children }: { tab?: Tab; children: ReactNode }) {
  const style = { "--nav-h": tab ? "68px" : "0px" } as CSSProperties;
  return (
    <div style={style} className="flex flex-1 flex-col">
      <main className="mx-auto w-full max-w-lg flex-1 px-5 pb-[calc(var(--nav-h)+104px)]">
        <Suspense fallback={<Loading />}>
          <RequireSession>{children}</RequireSession>
        </Suspense>
      </main>
      {tab && <BottomNav active={tab} />}
    </div>
  );
}
