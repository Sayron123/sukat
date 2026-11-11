import type { Metadata } from "next";
import { notFound, redirect } from "next/navigation";
import { Suspense } from "react";

import { AppPage } from "@/components/app-page";
import { PageHeader } from "@/components/page-header";
import { Avatar, Badge, Card, Loading, Notice } from "@/components/ui";
import { STORE_TZ } from "@/lib/dates";
import { backendFetch, getToken } from "@/lib/server/backend";
import type { Me, Staff } from "@/lib/types";

import { AliasForm } from "./member-forms";

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
  const canRename = !member.is_owner || member.user_id === me.user_id;
  const joined = new Date(member.created_at).toLocaleDateString("en-PH", {
    timeZone: STORE_TZ,
    year: "numeric",
    month: "long",
    day: "numeric",
  });
  const details = [
    { label: "Account name", value: member.full_name },
    { label: "Email", value: member.email },
    { label: "Joined", value: joined },
  ];

  return (
    <>
      <PageHeader eyebrow="Staff" title={name} back="/staff" />
      <Card className="mb-4">
        <div className="mb-4 flex items-center gap-3">
          <Avatar name={name} large />
          <div className="flex flex-wrap gap-1.5">
            <Badge className="capitalize">{member.is_owner ? "owner" : member.role}</Badge>
            {!member.active && <Badge tone="red">Inactive</Badge>}
          </div>
        </div>
        <dl className="flex flex-col gap-3">
          {details.map((d) => (
            <div key={d.label} className="min-w-0">
              <dt className="text-[13px] text-muted">{d.label}</dt>
              <dd className="truncate text-[15px] text-text">{d.value}</dd>
            </div>
          ))}
        </dl>
      </Card>
      {canRename && <AliasForm memberId={member.member_id} alias={member.alias} />}
    </>
  );
}
