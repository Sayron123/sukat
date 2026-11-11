"use client";

import { useEffect, useState, type FormEvent } from "react";

import { SaveResult, useSave } from "@/components/form-save";
import { Button, Card, Field } from "@/components/ui";
import { api } from "@/lib/api-client";
import type { Me } from "@/lib/types";

export function StoreForm() {
  const [me, setMe] = useState<Me | null>(null);
  const { pending, saved, error, save } = useSave("store", "PATCH", "Could not save the store.");

  useEffect(() => {
    api<Me>("auth/me").then(setMe, () => {});
  }, []);

  function onSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const form = new FormData(e.currentTarget);
    void save({ name: String(form.get("store_name") ?? ""), address: String(form.get("store_address") ?? "") });
  }

  if (me?.role !== "manager") return null;

  return (
    <Card>
      <h2 className="mb-4 text-base font-bold text-text">Store</h2>
      <form onSubmit={onSubmit} className="flex flex-col gap-4">
        <Field
          id="store_name"
          name="store_name"
          label="Store name"
          defaultValue={me.store_name}
          maxLength={120}
          autoComplete="organization"
          pattern=".*\S.*"
          title="Enter the store name"
          required
        />
        <Field
          id="store_address"
          name="store_address"
          label="Address (optional)"
          defaultValue={me.store_address ?? ""}
          maxLength={300}
          autoComplete="street-address"
        />
        <SaveResult saved={saved} error={error} />
        <Button type="submit" disabled={pending}>
          {pending ? "Please wait…" : "Save store"}
        </Button>
      </form>
    </Card>
  );
}
