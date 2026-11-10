"use client";

import { useState, type ChangeEvent } from "react";

import { Select } from "@/components/ui";
import { ApiError, api } from "@/lib/api-client";
import type { Role } from "@/lib/types";

const ROLES: Role[] = ["manager", "secretary", "member"];

export function RoleSelect({ memberId, name, role }: { memberId: string; name: string; role: Role }) {
  const [value, setValue] = useState(role);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function onChange(e: ChangeEvent<HTMLSelectElement>) {
    const next = e.target.value as Role;
    setError(null);
    setPending(true);
    try {
      await api(`staff/${memberId}/role`, { method: "PATCH", body: JSON.stringify({ role: next }) });
      setValue(next);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not change the role.");
    } finally {
      setPending(false);
    }
  }

  return (
    <div className="w-32">
      <Select
        id={`role-${memberId}`}
        label={`Role for ${name}`}
        hideLabel
        value={value}
        disabled={pending}
        onChange={onChange}
      >
        {ROLES.map((r) => (
          <option key={r} value={r}>
            {r}
          </option>
        ))}
      </Select>
      {error && (
        <p role="alert" className="mt-1 text-[13px] text-red">
          {error}
        </p>
      )}
    </div>
  );
}
