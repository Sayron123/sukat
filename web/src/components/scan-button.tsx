"use client";

import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";

import { api } from "@/lib/api-client";
import type { Me } from "@/lib/types";

import { Icon } from "./icons";
import { ScanModeSheet } from "./scan-mode-sheet";
import { buttonClass } from "./ui";

export function ScanButton() {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const request = useRef<Promise<Me | null> | null>(null);

  function loadMe() {
    request.current ??= api<Me>("auth/me").catch(() => {
      request.current = null;
      return null;
    });
    return request.current;
  }

  useEffect(() => {
    void loadMe();
  }, []);

  async function start() {
    const me = await loadMe();
    if (me?.role === "member") router.push("/scan/sale");
    else setOpen(true);
  }

  return (
    <>
      <button type="button" onClick={start} className={buttonClass("primary", "lg")}>
        <Icon name="camera" />
        Scan
      </button>
      <ScanModeSheet open={open} onClose={() => setOpen(false)} />
    </>
  );
}
