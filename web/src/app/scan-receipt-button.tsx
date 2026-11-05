"use client";

import { useRouter } from "next/navigation";
import { useRef } from "react";

import { setPendingPhoto } from "@/lib/pending-photo";

/**
 * Opens the camera straight away (the tap goes directly to the file input; browsers
 * don't allow opening it later from code), then continues on /scan/sale with the photo.
 * If the visitor isn't logged in, the upload there sends them to the login page.
 */
export function ScanReceiptButton() {
  const router = useRouter();
  const input = useRef<HTMLInputElement>(null);
  return (
    <>
      <input
        ref={input}
        type="file"
        accept="image/*"
        capture="environment"
        className="hidden"
        aria-hidden
        tabIndex={-1}
        onChange={(e) => {
          const file = e.target.files?.[0];
          e.target.value = "";
          if (!file) return;
          setPendingPhoto(file);
          router.push("/scan/sale");
        }}
      />
      <button
        type="button"
        onClick={() => input.current?.click()}
        className="flex h-14 w-full items-center justify-center rounded-button bg-accent text-base font-medium text-white hover:bg-accent-pressed active:bg-accent-pressed"
      >
        Scan Receipt
      </button>
    </>
  );
}
