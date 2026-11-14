"use client";

import { MascotMessage } from "@/components/mascot";
import { Button } from "@/components/ui";

export default function ErrorPage({ retry }: { error: unknown; retry: () => void }) {
  return (
    <main className="mx-auto flex w-full max-w-lg flex-1 flex-col items-center justify-center gap-4 px-6 py-16">
      <MascotMessage emote="error" size={140} title="Something went wrong">
        Sukat could not open this page. Try again, or go back and open it from the menu.
      </MascotMessage>
      <Button type="button" onClick={retry} className="max-w-xs">
        Try again
      </Button>
    </main>
  );
}
