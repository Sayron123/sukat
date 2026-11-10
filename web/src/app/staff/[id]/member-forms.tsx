"use client";

import type { FormEvent } from "react";

import { SaveResult, useSave } from "@/components/form-save";
import { Button, Card, Field, Select } from "@/components/ui";
import { ATTENDANCE_LABELS, type AttendanceStatus } from "@/lib/types";

const STATUSES = Object.keys(ATTENDANCE_LABELS) as AttendanceStatus[];

export function AliasForm({ memberId, alias }: { memberId: string; alias: string | null }) {
  const { pending, saved, error, save } = useSave(`staff/${memberId}/alias`, "PATCH", "Could not save the name.");

  function onSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    void save({ alias: String(new FormData(e.currentTarget).get("alias") ?? "") });
  }

  return (
    <Card className="mb-4">
      <form onSubmit={onSubmit} className="flex flex-col gap-4">
        <Field
          id="alias"
          name="alias"
          label="Name or alias in this store"
          defaultValue={alias ?? ""}
          maxLength={120}
          autoComplete="off"
          hint="Leave empty to use their account name."
        />
        <SaveResult saved={saved} error={error} />
        <Button type="submit" disabled={pending}>
          {pending ? "Please wait…" : "Save name"}
        </Button>
      </form>
    </Card>
  );
}

export function AttendanceForm({ memberId, today }: { memberId: string; today: string }) {
  const { pending, saved, error, save } = useSave(
    `staff/${memberId}/attendance`,
    "POST",
    "Could not save attendance.",
  );

  function onSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const { work_date, status, note } = Object.fromEntries(new FormData(e.currentTarget));
    void save({ work_date, status, note });
  }

  return (
    <Card className="mb-4">
      <form onSubmit={onSubmit} className="flex flex-col gap-4">
        <b className="block text-base text-text">Add attendance</b>
        <Field
          id="work_date"
          name="work_date"
          type="date"
          label="Date"
          defaultValue={today}
          max={today}
          required
          hint="Saving the same date again replaces it."
        />
        <Select id="status" name="status" label="Status" defaultValue="present">
          {STATUSES.map((s) => (
            <option key={s} value={s}>
              {ATTENDANCE_LABELS[s]}
            </option>
          ))}
        </Select>
        <Field id="note" name="note" label="Note (optional)" maxLength={300} autoComplete="off" />
        <SaveResult saved={saved} error={error} />
        <Button type="submit" disabled={pending}>
          {pending ? "Please wait…" : "Save attendance"}
        </Button>
      </form>
    </Card>
  );
}
