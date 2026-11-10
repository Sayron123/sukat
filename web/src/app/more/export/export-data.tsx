"use client";

import { useEffect, useState } from "react";

import { Icon } from "@/components/icons";
import { PageHeader } from "@/components/page-header";
import { Loading, Notice } from "@/components/ui";
import { api } from "@/lib/api-client";
import type { Me } from "@/lib/types";

const FILES = [
  { path: "products", title: "Products", detail: "Every product with other names, price, stock and alert level" },
  { path: "transactions", title: "Transactions", detail: "Every sale, delivery and adjustment, one row per item" },
  { path: "stock-movements", title: "Stock movements", detail: "Every stock change with the stock after it" },
];

export function ExportData() {
  const [me, setMe] = useState<Me | null | "error">(null);
  useEffect(() => {
    api<Me>("auth/me").then(setMe, () => setMe("error"));
  }, []);

  if (me === null) return <Loading />;
  if (me === "error") return <p className="pt-8 text-red">Could not load your account.</p>;

  return (
    <>
      <PageHeader eyebrow={me.store_name} title="Download store data" back="/more" />
      {me.role !== "manager" ? (
        <Notice icon="users" title="Managers only">
          Only the store manager can download the store&apos;s data.
        </Notice>
      ) : (
        <>
          <p className="mb-4 text-sm text-muted">
            CSV files of everything saved for {me.store_name}. They open in Excel or Google Sheets.
            Keep them safe: they include your staff&apos;s names and your sales.
          </p>
          <ul className="border-t border-border">
            {FILES.map((f) => (
              <li key={f.path}>
                <a
                  href={`/api/backend/exports/${f.path}`}
                  download
                  className="flex min-h-[72px] items-center gap-3 border-b border-border text-text"
                >
                  <span className="grid h-10 w-8 place-items-center">
                    <Icon name="download" size={21} />
                  </span>
                  <span className="min-w-0 flex-1">
                    <b className="block text-base">{f.title}</b>
                    <small className="mt-1 block text-sm text-muted">{f.detail}</small>
                  </span>
                </a>
              </li>
            ))}
          </ul>
        </>
      )}
    </>
  );
}
