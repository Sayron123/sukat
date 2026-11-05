import type { Metadata } from "next";
import { redirect } from "next/navigation";

import { AppPage } from "@/components/app-page";
import { PageHeader } from "@/components/page-header";
import { Avatar, Badge, Card, Notice } from "@/components/ui";
import { backendFetch, getToken } from "@/lib/server/backend";

export const metadata: Metadata = { title: "Staff · Sukat" };

type Staff = {
  member_id: string;
  email: string;
  full_name: string;
  role: string;
  active: boolean;
};

export default function StaffPage() {
  return (
    <AppPage>
      <StaffContent />
    </AppPage>
  );
}

async function StaffContent() {
  const token = await getToken();
  if (!token) redirect("/login");

  let meRes: Response;
  let staffRes: Response;
  try {
    [meRes, staffRes] = await Promise.all([
      backendFetch("/auth/me", { token }),
      backendFetch("/staff", { token }),
    ]);
  } catch {
    // fetch() throws (instead of returning a status) when the API cannot be reached.
    return <ApiDown />;
  }
  // Expired, invalid, or deactivated: the cookie is no longer useful.
  if (meRes.status === 401) redirect("/login");
  if (!meRes.ok) throw new Error("Could not load your account");
  const staff = staffRes.ok ? ((await staffRes.json()) as Staff[]) : null;

  return (
    <>
      <PageHeader
        eyebrow={staff ? `${staff.length} ${staff.length === 1 ? "person" : "people"}` : " "}
        title="Staff"
        back="/more"
      />
      {staffRes.status === 403 ? (
        <Card className="text-sm text-muted">Only managers and secretaries can see the staff list.</Card>
      ) : !staff ? (
        <p className="text-sm text-red">Could not load staff.</p>
      ) : (
        <StaffList staff={staff} />
      )}
      <Notice icon="users" title="Roles control access" className="mt-5">
        Managers and secretaries can edit products and void sales. Members can scan sales and stock.
      </Notice>
    </>
  );
}

function ApiDown() {
  return (
    <>
      <PageHeader title="Staff" back="/more" />
      <Notice title="API not reachable">
        The Sukat server is not responding. Check that it is running, then reload this page.
      </Notice>
    </>
  );
}

function StaffList({ staff }: { staff: Staff[] }) {
  return (
    <ul className="rounded-card border border-border px-4 py-1">
      {staff.map((s) => (
        <li key={s.member_id} className="flex min-h-[84px] items-center gap-2.5">
          <Avatar name={s.full_name} />
          <div className="min-w-0 flex-1">
            <b className="block truncate text-base text-text">{s.full_name}</b>
            <small className="mt-1 block truncate text-[13px] text-muted">{s.email}</small>
          </div>
          <div className="flex shrink-0 flex-col items-end gap-1">
            <Badge className="capitalize">{s.role}</Badge>
            {!s.active && <Badge tone="red">Inactive</Badge>}
          </div>
        </li>
      ))}
    </ul>
  );
}
