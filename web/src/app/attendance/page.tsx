import type { Metadata } from "next";
import { redirect } from "next/navigation";
import { connection } from "next/server";
import { Suspense } from "react";

import { AppPage } from "@/components/app-page";
import { PageHeader } from "@/components/page-header";
import { Loading, Notice } from "@/components/ui";
import { addDays, storeDate } from "@/lib/dates";
import { backendFetch, getToken } from "@/lib/server/backend";
import { canEditProducts, type DayAttendance, type Me, type Staff } from "@/lib/types";

import { AttendanceCalendar } from "./attendance-calendar";

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

function isRealDay(value: string) {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value)) return false;
  const parsed = new Date(`${value}T00:00:00Z`);
  return !Number.isNaN(parsed.getTime()) && parsed.toISOString().slice(0, 10) === value;
}

async function AttendanceContent({ searchParams }: { searchParams: SearchParams }) {
  const token = await getToken();
  if (!token) redirect("/login");

  const { date } = await searchParams;
  await connection();
  const today = storeDate();
  const asked = typeof date === "string" && isRealDay(date) ? date : today;
  const day = asked > today ? today : asked;
  const monthStart = `${day.slice(0, 8)}01`;
  const monthEnd = addDays(`${addDays(monthStart, 31).slice(0, 8)}01`, -1);

  let meRes: Response;
  let staffRes: Response;
  let monthRes: Response;
  try {
    [meRes, staffRes, monthRes] = await Promise.all([
      backendFetch("/auth/me", { token }),
      backendFetch("/staff", { token }),
      backendFetch(`/attendance?start=${monthStart}&end=${monthEnd}`, { token }),
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
  if (!canEditProducts(me.role)) redirect("/more");
  if (!staffRes.ok || !monthRes.ok) throw new Error("Could not load attendance");
  const staff = ((await staffRes.json()) as Staff[]).filter((s) => s.active);
  const marks = (await monthRes.json()) as DayAttendance[];

  return <AttendanceCalendar key={monthStart} day={day} today={today} staff={staff} marks={marks} />;
}
