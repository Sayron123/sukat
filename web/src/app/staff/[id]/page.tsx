import type { Metadata } from "next";
import { notFound, redirect } from "next/navigation";
import { Suspense } from "react";

import { AppPage } from "@/components/app-page";
import { PageHeader } from "@/components/page-header";
import { Avatar, Badge, Loading, Notice } from "@/components/ui";
import { STORE_TZ } from "@/lib/dates";
import { backendFetch, getToken } from "@/lib/server/backend";
import type { Me, Staff } from "@/lib/types";

import { MemberEditor } from "./member-editor";

export const metadata: Metadata = { title: "Staff member · Sukat" };

const UUID_PATTERN = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

export default function StaffMemberPage({ params }: PageProps<"/staff/[id]">) {
  return (
    <AppPage>
      <Suspense fallback={<Loading />}>
        <MemberContent params={params} />
      </Suspense>
    </AppPage>
  );
}

async function MemberContent({ params }: { params: PageProps<"/staff/[id]">["params"] }) {
  const { id } = await params;
  if (!UUID_PATTERN.test(id)) notFound();
  const token = await getToken();
  if (!token) redirect("/login");

  let meRes: Response;
  let memberRes: Response;
  try {
    [meRes, memberRes] = await Promise.all([
      backendFetch("/auth/me", { token }),
      backendFetch(`/staff/${id}`, { token }),
    ]);
  } catch {
    return (
      <>
        <PageHeader title="Staff member" back="/staff" />
        <Notice title="API not reachable">
          The Sukat server is not responding. Check that it is running, then reload this page.
        </Notice>
      </>
    );
  }
  if (meRes.status === 401) redirect("/login");
  if (!meRes.ok) throw new Error("Could not load your account");
  const me = (await meRes.json()) as Me;
  if (me.role !== "manager") redirect("/staff");
  if (memberRes.status === 404) notFound();
  if (!memberRes.ok) throw new Error("Could not load this staff member");
  const member = (await memberRes.json()) as Staff;

  const name = member.alias ?? member.full_name;
  const self = member.user_id === me.user_id;
  const canRename = !member.is_owner || self;
  const canChange = member.active && !member.is_owner && !self;
  const joined = new Date(member.created_at).toLocaleDateString("en-PH", {
    timeZone: STORE_TZ,
    month: "short",
    day: "numeric",
    year: "numeric",
  });
  const detail = [member.alias && member.full_name, member.email ?? (member.username && `@${member.username}`)]
    .filter(Boolean)
    .join(" · ");

  return (
    <>
      <PageHeader title={name} back="/staff" />
      <div className="mb-6 flex items-center gap-3 rounded-card border border-border bg-surface px-4 py-3">
        <Avatar name={name} large accent={member.is_owner} />
        <div className="min-w-0 flex-1">
          <b className="block truncate text-base text-text">{name}</b>
          {detail && <small className="mt-0.5 block truncate text-[13px] text-muted">{detail}</small>}
          <small className="mt-0.5 block text-[13px] text-muted">Joined {joined}</small>
        </div>
        {!member.active && <Badge tone="red">Inactive</Badge>}
      </div>
      <MemberEditor member={member} storeName={me.store_name} canChange={canChange} canRename={canRename} />
    </>
  );
}
