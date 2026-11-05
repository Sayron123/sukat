import type { Metadata } from "next";

import { AppPage } from "@/components/app-page";

import { ReviewList } from "./review-list";

export const metadata: Metadata = { title: "Needs review · Sukat" };

export default function NeedsReviewPage() {
  return (
    <AppPage>
      <ReviewList />
    </AppPage>
  );
}
