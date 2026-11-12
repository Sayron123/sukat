"use client";

import { useRouter } from "next/navigation";
import { useState, type ChangeEvent } from "react";

import { useSavedFlag } from "@/components/form-save";
import { SavedStatus, Select } from "@/components/ui";
import { ApiError, api } from "@/lib/api-client";
import type { Role } from "@/lib/types";

const ROLES: Role[] = ["manager", "secretary", "member"];

export function RoleSelect({ memberId, name, role }: { memberId: string; name: string; role: Role }) {
  const router = useRouter();
  const [value, setValue] = useState(role);
  const [pending, setPending] = useState(false);
  const [saved, setSaved] = useSavedFlag();
  const [error, setError] = useState<string | null>(null);

  async function onChange(e: ChangeEvent<HTMLSelectElement>) {
    const next = e.target.value as Role;
    setError(null);
    setSaved(false);
    setPending(true);
    try {
      await api(`staff/${memberId}/role`, { method: "PATCH", body: JSON.stringify({ role: next }) });
      setValue(next);
      setSaved(true);
      router.refresh();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not change the role.");
    } finally {
      setPending(false);
    }
  }

  return (
    <div className="flex w-32 flex-col items-end gap-1">
      <Select
        id={`role-${memberId}`}
        label={`Role for ${name}`}
        hideLabel
        value={value}
        disabled={pending}
        onChange={onChange}
        wrapperClassName="w-full"
      >
        {ROLES.map((r) => (
          <option key={r} value={r}>
            {r}
          </option>
        ))}
      </Select>
      <SavedStatus show={saved} />
      {error && (
        <p role="alert" className="text-[13px] text-red">
          {error}
        </p>
      )}
    </div>
  );
}
