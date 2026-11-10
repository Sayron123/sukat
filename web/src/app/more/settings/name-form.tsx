"use client";

import { useEffect, useState, type FormEvent } from "react";

import { SaveResult, useSave } from "@/components/form-save";
import { Button, Field, Loading } from "@/components/ui";
import { api } from "@/lib/api-client";
import type { Me } from "@/lib/types";

export function NameForm() {
  const [me, setMe] = useState<Me | null | "error">(null);
  const { pending, saved, error, save } = useSave("auth/me", "PATCH", "Could not save your name.");

  useEffect(() => {
    api<Me>("auth/me").then(setMe, () => setMe("error"));
  }, []);

  function onSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    void save({ full_name: String(new FormData(e.currentTarget).get("full_name") ?? "") });
  }

  if (me === null) return <Loading />;
  if (me === "error") return <p className="text-sm text-red">Could not load your account.</p>;

  return (
    <form onSubmit={onSubmit} className="flex flex-col gap-4">
      <Field
        id="full_name"
        name="full_name"
        label="Name"
        defaultValue={me.full_name}
        maxLength={120}
        autoComplete="name"
        pattern=".*\S.*"
        title="Enter your name"
        required
      />
      <SaveResult saved={saved} error={error} />
      <Button type="submit" disabled={pending}>
        {pending ? "Please wait…" : "Save name"}
      </Button>
    </form>
  );
}
