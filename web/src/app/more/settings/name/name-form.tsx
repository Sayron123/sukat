"use client";

import { useEffect, useState, type FormEvent } from "react";

import { Field, Loading } from "@/components/ui";
import { api } from "@/lib/api-client";
import type { Me } from "@/lib/types";

import { EditActions, useSaveAndReturn } from "../edit-actions";

const FORM = "name-form";

export function NameForm() {
  const [me, setMe] = useState<Me | null | "error">(null);
  const { pending, error, setError, save } = useSaveAndReturn("auth/me", "Could not save your name.", "Name saved");

  useEffect(() => {
    api<Me>("auth/me").then(setMe, () => setMe("error"));
  }, []);

  function onSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    void save({ full_name: String(new FormData(e.currentTarget).get("full_name") ?? "").trim() });
  }

  return (
    <>
      {me === null && <Loading />}
      {me === "error" && <p className="text-sm text-red">Could not load your account.</p>}
      {me !== null && me !== "error" && (
        <form id={FORM} onSubmit={onSubmit} onChange={() => setError(null)}>
          <Field
            id="full_name"
            name="full_name"
            label="Name"
            defaultValue={me.full_name}
            placeholder="e.g. Juan Dela Cruz"
            hint="This name shows on sales and stock records you make."
            maxLength={120}
            autoComplete="name"
            pattern=".*\S.*"
            title="Enter your name"
            required
          />
        </form>
      )}
      <EditActions form={FORM} label="Save name" pending={pending || me === null} error={error} />
    </>
  );
}
