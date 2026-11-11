import type { Metadata } from "next";

import { AppPage } from "@/components/app-page";

import { RecycleBin } from "./recycle-bin";

export const metadata: Metadata = { title: "Recycle bin · Sukat" };

export default function RecycleBinPage() {
  return (
    <AppPage>
      <RecycleBin />
    </AppPage>
  );
}
