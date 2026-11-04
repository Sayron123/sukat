"use client";

import { useEffect, useState } from "react";

type Status = "checking" | "connected" | "unreachable";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export function ApiStatus() {
  const [status, setStatus] = useState<Status>("checking");

  useEffect(() => {
    const controller = new AbortController();
    fetch(`${API_URL}/health`, { signal: controller.signal, cache: "no-store" })
      .then(async (res) => {
        const body: unknown = await res.json().catch(() => null);
        const ok =
          res.ok && typeof body === "object" && body !== null && "db" in body && body.db === "ok";
        setStatus(ok ? "connected" : "unreachable");
      })
      .catch((err: unknown) => {
        if (err instanceof DOMException && err.name === "AbortError") return;
        setStatus("unreachable");
      });
    return () => controller.abort();
  }, []);

  const styles: Record<Status, { dot: string; text: string }> = {
    checking: { dot: "bg-amber", text: "Checking API…" },
    connected: { dot: "bg-green", text: "API connected" },
    unreachable: { dot: "bg-red", text: "API not reachable" },
  };

  return (
    <p role="status" className="flex items-center gap-2 text-text">
      <span className={`h-2.5 w-2.5 rounded-full ${styles[status].dot}`} aria-hidden />
      {styles[status].text}
    </p>
  );
}
