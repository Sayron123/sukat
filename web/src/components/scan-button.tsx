"use client";

import { useState } from "react";

import { Icon } from "./icons";
import { ScanModeSheet } from "./scan-mode-sheet";
import { buttonClass } from "./ui";

export function ScanButton() {
  const [open, setOpen] = useState(false);
  return (
    <>
      <button type="button" onClick={() => setOpen(true)} className={buttonClass("primary", "lg")}>
        <Icon name="camera" />
        Scan
      </button>
      <ScanModeSheet open={open} onClose={() => setOpen(false)} />
    </>
  );
}
