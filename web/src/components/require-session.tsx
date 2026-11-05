import { redirect } from "next/navigation";
import type { ReactNode } from "react";

import { getToken } from "@/lib/server/backend";

/**
 * Server-side guard: send visitors without a session cookie to /login.
 * Reads cookies, so render it inside <Suspense>. The API still checks the token on
 * every request; this only avoids showing an empty page to logged-out visitors.
 */
export async function RequireSession({ children }: { children: ReactNode }) {
  if (!(await getToken())) redirect("/login");
  return <>{children}</>;
}
