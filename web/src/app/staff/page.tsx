import type { Metadata } from "next";
import Link from "next/link";
import { redirect } from "next/navigation";

import { AppPage } from "@/components/app-page";
import { Icon } from "@/components/icons";
import { PageHeader, headerTextActionClass } from "@/components/page-header";
import { Avatar, Badge, Notice } from "@/components/ui";
import { backendFetch, getToken } from "@/lib/server/backend";
import type { Me, Staff } from "@/lib/types";

import { RoleSelect } from "./role-select";

export const metadata: Metadata = { title: "Staff · Sukat" };

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
  const me = (await meRes.json()) as Me;
  const staff = staffRes.ok ? ((await staffRes.json()) as Staff[]) : null;

  return (
    <>
      <PageHeader
        eyebrow={staff ? `${staff.length} ${staff.length === 1 ? "person" : "people"}` : " "}
        title="Staff"
        back="/more"
        action={
          me.role !== "member" && (
            <Link href="/staff/invite" className={headerTextActionClass}>
              <Icon name="plus" size={20} />
              Invite
            </Link>
          )
        }
      />
      {!staff ? (
        <p className="text-sm text-red">Could not load staff.</p>
      ) : (
        <StaffList staff={staff} me={me} />
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

function StaffList({ staff, me }: { staff: Staff[]; me: Me }) {
  return (
    <ul className="rounded-card border border-border px-4 py-1">
      {staff.map((s) => {
        const name = s.alias ?? s.full_name;
        const detail = [s.alias && s.full_name, s.email].filter(Boolean).join(" · ");
        const person = (
          <>
            <Avatar name={name} />
            <div className="min-w-0 flex-1">
              <b className="block truncate text-base text-text">{name}</b>
              {detail && <small className="mt-1 block truncate text-[13px] text-muted">{detail}</small>}
            </div>
          </>
        );
        return (
          <li key={s.member_id} className="flex min-h-[84px] items-center gap-2.5">
            {me.role === "manager" ? (
              <Link href={`/staff/${s.member_id}`} className="flex min-w-0 flex-1 items-center gap-2.5">
                {person}
              </Link>
            ) : (
              <div className="flex min-w-0 flex-1 items-center gap-2.5">{person}</div>
            )}
            <div className="flex shrink-0 flex-col items-end gap-1">
              {me.role === "manager" && s.active && !s.is_owner && s.user_id !== me.user_id ? (
                <RoleSelect memberId={s.member_id} name={name} role={s.role} />
              ) : (
                <Badge className="capitalize">{s.is_owner ? "owner" : s.role}</Badge>
              )}
              {!s.active && <Badge tone="red">Inactive</Badge>}
            </div>
          </li>
        );
      })}
    </ul>
  );
}
