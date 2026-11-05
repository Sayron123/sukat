import type { Metadata } from "next";
import { Suspense } from "react";

import { AppPage } from "@/components/app-page";
import { Loading } from "@/components/ui";

import { ResumeReview } from "./resume-review";

export const metadata: Metadata = { title: "Review · Sukat" };

export default function ResumeReviewPage({ params }: PageProps<"/scan/review/[id]">) {
  return (
    <AppPage>
      <Suspense fallback={<Loading />}>
        <Loader params={params} />
      </Suspense>
    </AppPage>
  );
}

async function Loader({ params }: { params: PageProps<"/scan/review/[id]">["params"] }) {
  const { id } = await params;
  return <ResumeReview id={id} />;
}
