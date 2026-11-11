"use client";

import type { FormEvent } from "react";

import { SaveResult, useSave } from "@/components/form-save";
import { Button, Card, Field } from "@/components/ui";

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
