"use client";

import { useRouter } from "next/navigation";
import { useRef } from "react";

import { Icon } from "@/components/icons";
import { buttonClass } from "@/components/ui";
import { setPendingPhoto } from "@/lib/pending-photo";

/**
 * Opens the camera straight away (the tap goes directly to the file input; browsers
 * don't allow opening it later from code), then continues on /scan/sale with the photo.
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
        className={buttonClass("primary", "lg")}
      >
        <Icon name="camera" />
        Scan Receipt
      </button>
    </>
  );
}
