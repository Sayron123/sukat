import type { Metadata } from "next";
import { redirect } from "next/navigation";
import { Suspense } from "react";

import { LogoutButton } from "@/components/logout-button";
import { Card } from "@/components/ui";
import { backendFetch, getToken } from "@/lib/server/backend";

export const metadata: Metadata = { title: "Staff · Sukat" };

type Me = { full_name: string; store_name: string; role: string };
type Staff = {
  member_id: string;
  email: string;
  full_name: string;
  role: string;
  active: boolean;
};

export default function StaffPage() {
  return (
    <main className="mx-auto w-full max-w-2xl flex-1 p-4">
      <Suspense fallback={<p className="text-muted">Loading staff…</p>}>
        <StaffContent />
      </Suspense>
    </main>
  );
}

async function StaffContent() {
  const token = await getToken();
  if (!token) redirect("/login");

  const [meRes, staffRes] = await Promise.all([
    backendFetch("/auth/me", { token }),
    backendFetch("/staff", { token }),
  ]);
  // Expired, invalid, or deactivated: the cookie is no longer useful.
  if (meRes.status === 401) redirect("/login");
  if (!meRes.ok) throw new Error("Could not load your account");
  const me = (await meRes.json()) as Me;

  return (
    <div className="flex flex-col gap-4">
      <header className="flex items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold text-text">{me.store_name}</h1>
          <p className="text-sm text-muted">
            {me.full_name} · <span className="capitalize">{me.role}</span>
          </p>
        </div>
        <LogoutButton />
      </header>

      <Card padded={false}>
        <h2 className="border-b border-border px-6 py-4 font-semibold text-text">Staff</h2>
        {staffRes.status === 403 ? (
          <p className="px-6 py-4 text-sm text-muted">
            Only managers and secretaries can see the staff list.
          </p>
        ) : !staffRes.ok ? (
          <p className="px-6 py-4 text-sm text-red">Could not load staff.</p>
        ) : (
          <StaffList staff={(await staffRes.json()) as Staff[]} />
        )}
      </Card>
    </div>
  );
}

function StaffList({ staff }: { staff: Staff[] }) {
  return (
    <ul className="divide-y divide-border">
      {staff.map((s) => (
        <li key={s.member_id} className="flex items-center justify-between gap-4 px-6 py-4">
          <div className="min-w-0">
            <p className="truncate font-medium text-text">{s.full_name}</p>
            <p className="truncate text-sm text-muted">{s.email}</p>
          </div>
          <div className="flex shrink-0 items-center gap-2 text-sm">
            <span className="capitalize text-muted">{s.role}</span>
            <span
              className={`rounded-full px-2 py-0.5 text-xs font-medium ${
                s.active ? "bg-green/10 text-green" : "bg-red/10 text-red"
              }`}
            >
              {s.active ? "Active" : "Inactive"}
            </span>
          </div>
        </li>
      ))}
    </ul>
  );
}
