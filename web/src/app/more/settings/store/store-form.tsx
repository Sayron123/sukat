"use client";

import { useEffect, useState, type FormEvent } from "react";

import { Field, Loading, Notice } from "@/components/ui";
import { api } from "@/lib/api-client";
import type { Me } from "@/lib/types";

import { EditActions, useSaveAndReturn } from "../edit-actions";

const FORM = "store-form";

export function StoreForm() {
  const [me, setMe] = useState<Me | null | "error">(null);
  const { pending, error, setError, save } = useSaveAndReturn(
    "store",
    "Could not save the store.",
    "Store details saved",
  );

  useEffect(() => {
    api<Me>("auth/me").then(setMe, () => setMe("error"));
  }, []);

  function onSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const form = new FormData(e.currentTarget);
    void save({
      name: String(form.get("store_name") ?? "").trim(),
      address: String(form.get("store_address") ?? "").trim(),
    });
  }

  if (me === null) return <Loading />;
  if (me === "error") return <p className="text-sm text-red">Could not load your store.</p>;
  if (me.role !== "manager") {
    return (
      <Notice icon="lock" title="Only a manager can change these">
        Ask your store manager to update the store name or address.
      </Notice>
    );
  }

  return (
    <>
      <form id={FORM} onSubmit={onSubmit} onChange={() => setError(null)} className="flex flex-col gap-5">
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
        <p className="-mt-2 text-[13px] leading-snug text-subtle">Your staff see this name when they sign in.</p>
      </form>
      <EditActions form={FORM} label="Save changes" pending={pending} error={error} />
    </>
  );
}
