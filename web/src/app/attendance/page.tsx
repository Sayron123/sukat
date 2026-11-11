import type { Metadata } from "next";
import { redirect } from "next/navigation";
import { Suspense } from "react";

import { AppPage } from "@/components/app-page";
import { PageHeader } from "@/components/page-header";
import { Loading, Notice } from "@/components/ui";
import { storeDate } from "@/lib/dates";
import { backendFetch, getToken } from "@/lib/server/backend";
import type { DayAttendance, Me, Staff } from "@/lib/types";

import { AttendanceDay } from "./attendance-day";

export const metadata: Metadata = { title: "Attendance · Sukat" };

type SearchParams = Promise<{ date?: string | string[] }>;

export default function AttendancePage({ searchParams }: { searchParams: SearchParams }) {
  return (
    <AppPage>
      <Suspense fallback={<Loading />}>
        <AttendanceContent searchParams={searchParams} />
      </Suspense>
    </AppPage>
  );
}

async function AttendanceContent({ searchParams }: { searchParams: SearchParams }) {
  const today = storeDate();
  const { date } = await searchParams;
  const asked = typeof date === "string" && /^\d{4}-\d{2}-\d{2}$/.test(date) ? date : today;
  const day = asked > today ? today : asked;

  const token = await getToken();
  if (!token) redirect("/login");

  let meRes: Response;
  let staffRes: Response;
  let dayRes: Response;
  try {
    [meRes, staffRes, dayRes] = await Promise.all([
      backendFetch("/auth/me", { token }),
      backendFetch("/staff", { token }),
      backendFetch(`/attendance?work_date=${day}`, { token }),
    ]);
  } catch {
    return (
      <>
        <PageHeader title="Attendance" back="/more" />
        <Notice title="API not reachable">
          The Sukat server is not responding. Check that it is running, then reload this page.
        </Notice>
      </>
    );
  }
  if (meRes.status === 401) redirect("/login");
  if (!meRes.ok) throw new Error("Could not load your account");
  const me = (await meRes.json()) as Me;
  if (me.role !== "manager") redirect("/more");
  if (!staffRes.ok || !dayRes.ok) throw new Error("Could not load attendance");
  const staff = ((await staffRes.json()) as Staff[]).filter((s) => s.active);
  const marks = (await dayRes.json()) as DayAttendance[];

  return <AttendanceDay key={day} day={day} today={today} staff={staff} marks={marks} />;
}
