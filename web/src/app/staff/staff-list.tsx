"use client";

import Link from "next/link";
import { useState } from "react";

import { Avatar, Badge, Card, Chip } from "@/components/ui";
import type { Me, Role, Staff } from "@/lib/types";

import { RoleSelect } from "./role-select";

const FILTERS: { role: Role | null; label: string }[] = [
  { role: null, label: "All" },
  { role: "manager", label: "Managers" },
  { role: "secretary", label: "Secretaries" },
  { role: "member", label: "Members" },
];

const NONE: Record<Role, string> = {
  manager: "No managers.",
  secretary: "No secretaries yet.",
  member: "No members yet.",
};

export function StaffList({ staff, me }: { staff: Staff[]; me: Me }) {
  const [role, setRole] = useState<Role | null>(null);
  const shown = role ? staff.filter((s) => s.role === role) : staff;

  return (
    <>
      <div className="-mx-5 mb-4 flex gap-2 overflow-x-auto px-5 [scrollbar-width:none]" role="group" aria-label="Role">
        {FILTERS.map((f) => (
          <Chip key={f.label} selected={role === f.role} onClick={() => setRole(f.role)}>
            {f.label}
          </Chip>
        ))}
      </div>
      {role && shown.length === 0 ? (
        <Card className="text-center text-muted">{NONE[role]}</Card>
      ) : (
        <ul className="rounded-card border border-border px-4 py-1">
          {shown.map((s) => (
            <StaffRow key={s.member_id} s={s} me={me} />
          ))}
        </ul>
      )}
    </>
  );
}

function StaffRow({ s, me }: { s: Staff; me: Me }) {
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
    <li className="flex min-h-[84px] items-center gap-2.5 py-2">
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
}
