import type { Metadata } from "next";

import { AppPage } from "@/components/app-page";

import { ChatScreen } from "./chat-screen";

export const metadata: Metadata = { title: "Ask Sukat · Sukat" };

export default function AiPage() {
  return (
    <AppPage tab="ai">
      <ChatScreen />
    </AppPage>
  );
}
