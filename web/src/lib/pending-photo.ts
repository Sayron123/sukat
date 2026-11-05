"use client";

/**
 * Hands a photo from one page to the next without uploading it twice.
 *
 * The home page's "Scan Receipt" button opens the camera right away (a file input must
 * be tapped directly; browsers block opening it later from code), then navigates to
 * /scan/sale, which picks the photo up here. Lives in memory only: client-side
 * navigation keeps it; a full page reload clears it (the user just takes it again).
 */
let pending: File | null = null;

export function setPendingPhoto(file: File): void {
  pending = file;
}

/** Returns the waiting photo once, then forgets it. */
export function takePendingPhoto(): File | null {
  const file = pending;
  pending = null;
  return file;
}
