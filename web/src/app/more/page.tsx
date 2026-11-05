import type { Metadata } from "next";

import { AppPage } from "@/components/app-page";

import { MoreMenu } from "./more-menu";

export const metadata: Metadata = { title: "More · Sukat" };

export default function MorePage() {
  return (
    <AppPage tab="more">
      <MoreMenu />
    </AppPage>
  );
}
