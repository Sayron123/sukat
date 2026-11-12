"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState, useTransition, type ChangeEvent, type ReactNode } from "react";

import { Icon } from "@/components/icons";
import { PageHeader, headerIconClass } from "@/components/page-header";
import { Avatar, Card, Chip } from "@/components/ui";
import { ApiError, api } from "@/lib/api-client";
import { addDays, dayLabel, storeDate } from "@/lib/dates";
import { ATTENDANCE_LABELS, type AttendanceStatus, type DayAttendance, type Staff } from "@/lib/types";

const STATUSES = Object.keys(ATTENDANCE_LABELS) as AttendanceStatus[];
const WEEKDAYS = ["S", "M", "T", "W", "T", "F", "S"];
const MONTHS = Array.from({ length: 12 }, (_, i) =>
  new Date(Date.UTC(2000, i, 1)).toLocaleDateString("en-PH", { timeZone: "UTC", month: "long" }),
);

type Mark = { status: AttendanceStatus; note: string | null };
type Month = Record<string, Record<string, Mark>>;
type DayState = "all-present" | "issue" | "partial" | "none";

const DAY_STATE_LABELS: Record<DayState, string> = {
  "all-present": ", everyone present",
  issue: ", someone late, on a half day or absent",
  partial: ", not finished",
  none: "",
};

const navClass =
  "grid h-11 w-11 place-items-center rounded-button text-text hover:bg-surface aria-disabled:pointer-events-none aria-disabled:opacity-30";

const todayClass =
  "flex h-11 shrink-0 items-center rounded-button px-2 text-[15px] font-semibold text-text hover:bg-surface";

const pickerClass =
  "h-11 cursor-pointer appearance-none rounded-button bg-transparent pr-7 pl-2 text-lg font-bold text-text field-sizing-content hover:bg-surface focus-visible:bg-surface";

function monthDays(monthStart: string): string[] {
  const days: string[] = [];
  for (let d = monthStart; d.slice(0, 7) === monthStart.slice(0, 7); d = addDays(d, 1)) days.push(d);
  return days;
}

function shiftMonth(monthStart: string, by: number): string {
  const d = new Date(`${monthStart}T00:00:00Z`);
  d.setUTCMonth(d.getUTCMonth() + by);
  return d.toISOString().slice(0, 10);
}

function monthTitle(monthStart: string): string {
  return new Date(`${monthStart}T00:00:00Z`).toLocaleDateString("en-PH", {
    timeZone: "UTC",
    month: "long",
    year: "numeric",
  });
}

function monthHref(year: number, month: number, today: string): string {
  const target = `${year}-${String(month).padStart(2, "0")}`;
  return target >= today.slice(0, 7) ? "/attendance" : `/attendance?date=${target}-01`;
}

function Picker({
  label,
  value,
  onChange,
  children,
}: {
  label: string;
  value: number;
  onChange: (e: ChangeEvent<HTMLSelectElement>) => void;
  children: ReactNode;
}) {
  return (
    <span className="relative flex">
      <select aria-label={label} defaultValue={value} onChange={onChange} className={pickerClass}>
        {children}
      </select>
      <Icon name="down" size={16} className="pointer-events-none absolute top-1/2 right-2 -translate-y-1/2" />
    </span>
  );
}

export function AttendanceCalendar({
  day,
  today,
  staff,
  marks,
}: {
  day: string;
  today: string;
  staff: Staff[];
  marks: DayAttendance[];
}) {
  const router = useRouter();
  const [navigating, startNavigation] = useTransition();
  const monthStart = `${day.slice(0, 8)}01`;
  const shownYear = Number(monthStart.slice(0, 4));
  const shownMonth = Number(monthStart.slice(5, 7));
  const thisYear = Number(today.slice(0, 4));
  const thisMonthNumber = Number(today.slice(5, 7));
  const firstYear = Math.min(
    shownYear,
    ...staff.map((s) => Number(storeDate(new Date(s.created_at)).slice(0, 4))),
  );
  const years = Array.from({ length: thisYear - firstYear + 1 }, (_, i) => thisYear - i);
  const [selected, setSelected] = useState(day);
  const [month, setMonth] = useState<Month>(() => {
    const byDay: Month = {};
    for (const m of marks) (byDay[m.work_date] ??= {})[m.member_id] = { status: m.status, note: m.note };
    return byDay;
  });
  const [pending, setPending] = useState<ReadonlySet<string>>(new Set());
  const [errors, setErrors] = useState<Record<string, string>>({});

  const days = monthDays(monthStart);
  const leading = new Date(`${monthStart}T00:00:00Z`).getUTCDay();
  const prevMonth = shiftMonth(monthStart, -1);
  const nextMonth = shiftMonth(monthStart, 1);
  const thisMonth = today.slice(0, 7) === monthStart.slice(0, 7);
  const selectedMarks = month[selected] ?? {};
  const marked = staff.filter((s) => selectedMarks[s.member_id]).length;

  function goTo(y: number, m: number) {
    startNavigation(() => router.push(monthHref(y, m, today)));
  }

  function dayState(d: string): DayState {
    const dayMarks = month[d];
    if (!dayMarks || staff.length === 0) return "none";
    const statuses = staff.map((s) => dayMarks[s.member_id]?.status);
    if (statuses.some((st) => st && st !== "present")) return "issue";
    if (statuses.every((st) => st === "present")) return "all-present";
    return statuses.some(Boolean) ? "partial" : "none";
  }

  function setMark(d: string, memberId: string, mark: Mark | undefined) {
    setMonth((m) => {
      const dayMarks = { ...m[d] };
      if (mark) dayMarks[memberId] = mark;
      else delete dayMarks[memberId];
      return { ...m, [d]: dayMarks };
    });
  }

  async function save(memberId: string, status: AttendanceStatus) {
    const d = selected;
    const before = month[d]?.[memberId];
    const key = `${d}:${memberId}`;
    setMark(d, memberId, { status, note: before?.note ?? null });
    setErrors((e) => ({ ...e, [key]: "" }));
    setPending((p) => new Set(p).add(key));
    try {
      await api(`staff/${memberId}/attendance`, {
        method: "POST",
        body: JSON.stringify({ work_date: d, status, note: before?.note ?? null }),
      });
    } catch (err) {
      setMark(d, memberId, before);
      setErrors((e) => ({
        ...e,
        [key]: err instanceof ApiError ? err.message : "Could not save attendance.",
      }));
    } finally {
      setPending((p) => {
        const rest = new Set(p);
        rest.delete(key);
        return rest;
      });
    }
  }

  return (
    <>
      <PageHeader
        eyebrow={staff.length ? `${staff.length} ${staff.length === 1 ? "person" : "people"}` : " "}
        title="Attendance"
        back="/more"
        action={
          <div className="flex shrink-0 items-center gap-1">
            {!thisMonth && (
              <Link href="/attendance" className={todayClass}>
                Today
              </Link>
            )}
            <Link href="/staff/invite" aria-label="Invite staff" title="Invite staff" className={`-mr-2 ${headerIconClass}`}>
              <Icon name="plus" size={20} />
            </Link>
          </div>
        }
      />

      <Card aria-busy={navigating || undefined} className={navigating ? "opacity-60 transition-opacity" : ""}>
        <div className="mb-3 flex items-center justify-between gap-2">
          <h2 className="sr-only">{monthTitle(monthStart)}</h2>
          <div className="-ml-2 flex min-w-0 items-center">
            <Picker label="Month" value={shownMonth} onChange={(e) => goTo(shownYear, Number(e.target.value))}>
              {MONTHS.map((name, i) => (
                <option key={name} value={i + 1} disabled={shownYear === thisYear && i + 1 > thisMonthNumber}>
                  {name}
                </option>
              ))}
            </Picker>
            <Picker label="Year" value={shownYear} onChange={(e) => goTo(Number(e.target.value), shownMonth)}>
              {years.map((y) => (
                <option key={y} value={y}>
                  {y}
                </option>
              ))}
            </Picker>
          </div>
          <div className="-mr-2 flex shrink-0 items-center">
            <Link href={`/attendance?date=${prevMonth}`} aria-label="Previous month" className={navClass}>
              <Icon name="arrow" size={20} />
            </Link>
            <Link
              href={`/attendance?date=${nextMonth}`}
              aria-label="Next month"
              aria-disabled={thisMonth || undefined}
              tabIndex={thisMonth ? -1 : undefined}
              className={navClass}
            >
              <Icon name="chevron" size={20} />
            </Link>
          </div>
        </div>

        <div className="grid grid-cols-7 text-center">
          {WEEKDAYS.map((w, i) => (
            <span key={i} className="pb-2 text-[13px] font-semibold text-muted" aria-hidden>
              {w}
            </span>
          ))}
          {Array.from({ length: leading }, (_, i) => (
            <span key={`blank-${i}`} />
          ))}
          {days.map((d) => {
            const future = d > today;
            const state = dayState(d);
            const isSelected = d === selected;
            return (
              <button
                key={d}
                type="button"
                disabled={future}
                onClick={() => setSelected(d)}
                aria-pressed={isSelected}
                aria-label={`${dayLabel(d)}${DAY_STATE_LABELS[state]}`}
                className="flex h-12 flex-col items-center justify-center gap-1 disabled:opacity-35"
              >
                <span
                  className={`grid h-8 w-8 place-items-center rounded-full text-sm font-semibold ${
                    isSelected
                      ? "bg-text text-inverse"
                      : state === "all-present"
                        ? "border-2 border-text text-text"
                        : "text-text"
                  } ${d === today && !isSelected ? "underline underline-offset-4" : ""}`}
                >
                  {Number(d.slice(8))}
                </span>
                <span
                  aria-hidden
                  className={`h-1.5 w-1.5 rounded-full ${
                    state === "issue" ? "bg-red" : state === "partial" ? "bg-muted" : "bg-transparent"
                  }`}
                />
              </button>
            );
          })}
        </div>

        <div className="mt-4 flex flex-wrap gap-x-4 gap-y-1 border-t border-border pt-3 text-[13px] text-muted">
          <span className="flex items-center gap-1.5">
            <span className="h-3.5 w-3.5 rounded-full border-2 border-text" aria-hidden />
            Everyone present
          </span>
          <span className="flex items-center gap-1.5">
            <span className="h-1.5 w-1.5 rounded-full bg-red" aria-hidden />
            Late, half day or absent
          </span>
          <span className="flex items-center gap-1.5">
            <span className="h-1.5 w-1.5 rounded-full bg-muted" aria-hidden />
            Not finished
          </span>
        </div>
      </Card>

      <h2 className="mt-8 mb-2 text-[13px] font-bold text-muted uppercase">
        {dayLabel(selected)} · {marked} of {staff.length} marked
      </h2>
      {staff.length === 0 ? (
        <Card className="text-sm text-muted">No active staff yet.</Card>
      ) : (
        <ul className="border-t border-border">
          {staff.map((s) => {
            const name = s.alias ?? s.full_name;
            const mark = selectedMarks[s.member_id];
            const key = `${selected}:${s.member_id}`;
            return (
              <li key={s.member_id} className="border-b border-border py-4">
                <div className="flex items-center gap-3">
                  <Avatar name={name} />
                  <span className="min-w-0 flex-1">
                    <b className="block truncate text-base text-text">{name}</b>
                    <small className="mt-0.5 block truncate text-[13px] text-muted">
                      {mark ? ATTENDANCE_LABELS[mark.status] : "Not marked"}
                      {mark?.note ? ` · ${mark.note}` : ""}
                    </small>
                  </span>
                </div>
                <div className="mt-3 flex flex-wrap gap-2" role="group" aria-label={`Attendance for ${name}`}>
                  {STATUSES.map((st) => (
                    <Chip
                      key={st}
                      selected={mark?.status === st}
                      disabled={pending.has(key)}
                      onClick={() => mark?.status !== st && save(s.member_id, st)}
                    >
                      {ATTENDANCE_LABELS[st]}
                    </Chip>
                  ))}
                </div>
                {errors[key] && (
                  <p role="alert" className="mt-2 text-sm text-red">
                    {errors[key]}
                  </p>
                )}
              </li>
            );
          })}
        </ul>
      )}
    </>
  );
}
