import type { Metadata } from "next";
import Link from "next/link";
import { redirect } from "next/navigation";

import { AppPage } from "@/components/app-page";
import { Icon } from "@/components/icons";
import { PageHeader, headerTextActionClass } from "@/components/page-header";
import { Notice } from "@/components/ui";
import { backendFetch, getToken } from "@/lib/server/backend";
import type { Me, Staff } from "@/lib/types";

import { StaffList } from "./staff-list";

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
