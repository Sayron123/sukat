"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { Icon } from "@/components/icons";
import { PageHeader, headerTextActionClass } from "@/components/page-header";
import { Avatar, Card, Chip, Field } from "@/components/ui";
import { ApiError, api } from "@/lib/api-client";
import { dayLabel } from "@/lib/dates";
import { ATTENDANCE_LABELS, type AttendanceStatus, type DayAttendance, type Staff } from "@/lib/types";

const STATUSES = Object.keys(ATTENDANCE_LABELS) as AttendanceStatus[];

export function AttendanceDay({
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
  const [status, setStatus] = useState<Record<string, AttendanceStatus>>(() =>
    Object.fromEntries(marks.map((m) => [m.member_id, m.status])),
  );
  const notes = Object.fromEntries(marks.map((m) => [m.member_id, m.note]));
  const [pending, setPending] = useState<ReadonlySet<string>>(new Set());
  const [errors, setErrors] = useState<Record<string, string>>({});

  async function mark(memberId: string, next: AttendanceStatus) {
    const before = status[memberId];
    setStatus((s) => ({ ...s, [memberId]: next }));
    setErrors((e) => ({ ...e, [memberId]: "" }));
    setPending((p) => new Set(p).add(memberId));
    try {
      await api(`staff/${memberId}/attendance`, {
        method: "POST",
        body: JSON.stringify({ work_date: day, status: next, note: notes[memberId] ?? null }),
      });
    } catch (err) {
      setStatus((s) => {
        const copy = { ...s };
        if (before) copy[memberId] = before;
        else delete copy[memberId];
        return copy;
      });
      setErrors((e) => ({
        ...e,
        [memberId]: err instanceof ApiError ? err.message : "Could not save attendance.",
      }));
    } finally {
      setPending((p) => {
        const rest = new Set(p);
        rest.delete(memberId);
        return rest;
      });
    }
  }

  const marked = staff.filter((s) => status[s.member_id]).length;

  return (
    <>
      <PageHeader
        eyebrow={staff.length ? `${marked} of ${staff.length} marked` : " "}
        title="Attendance"
        back="/more"
        action={
          <Link href="/staff/invite" className={headerTextActionClass}>
            <Icon name="plus" size={20} />
            Invite
          </Link>
        }
      />
      <Field
        id="attendance-day"
        type="date"
        label="Day"
        value={day}
        max={today}
        onChange={(e) => e.target.value && router.push(`/attendance?date=${e.target.value}`)}
        hint={dayLabel(day)}
      />
      {staff.length === 0 ? (
        <Card className="mt-5 text-sm text-muted">No active staff yet.</Card>
      ) : (
        <ul className="mt-5 border-t border-border">
          {staff.map((s) => {
            const name = s.alias ?? s.full_name;
            const current = status[s.member_id];
            return (
              <li key={s.member_id} className="border-b border-border py-4">
                <Link href={`/staff/${s.member_id}`} className="flex items-center gap-3 text-text">
                  <Avatar name={name} />
                  <span className="min-w-0 flex-1">
                    <b className="block truncate text-base">{name}</b>
                    <small className="mt-0.5 block truncate text-[13px] text-muted">
                      {current ? ATTENDANCE_LABELS[current] : "Not marked"}
                      {notes[s.member_id] ? ` · ${notes[s.member_id]}` : ""}
                    </small>
                  </span>
                  <Icon name="chevron" size={19} />
                </Link>
                <div className="mt-3 flex flex-wrap gap-2" role="group" aria-label={`Attendance for ${name}`}>
                  {STATUSES.map((st) => (
                    <Chip
                      key={st}
                      selected={current === st}
                      disabled={pending.has(s.member_id)}
                      onClick={() => current !== st && mark(s.member_id, st)}
                    >
                      {ATTENDANCE_LABELS[st]}
                    </Chip>
                  ))}
                </div>
                {errors[s.member_id] && (
                  <p role="alert" className="mt-2 text-sm text-red">
                    {errors[s.member_id]}
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
