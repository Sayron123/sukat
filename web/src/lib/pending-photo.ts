"use client";

/**
 * Hands a photo from one page to the next without uploading it twice.
 *
 * The home page's "Scan Receipt" button opens the camera right away (a file input must
 * be tapped directly; browsers block opening it later from code), then navigates to
 * /scan/sale, which picks the photo up here. Lives in memory only: client-side
 * navigation keeps it; a full page reload clears it (the user just takes it again).
 *
 * Listeners make it work whether the scan page mounts fresh or is still alive from an
 * earlier visit (Next.js can keep visited pages' components around).
 */
let pending: File | null = null;
const listeners = new Set<() => void>();

export function setPendingPhoto(file: File): void {
  pending = file;
  listeners.forEach((notify) => notify());
}

/** Returns the waiting photo once, then forgets it. */
export function takePendingPhoto(): File | null {
  const file = pending;
  pending = null;
  return file;
}

/** Call `onPhoto` with any waiting photo now, and with each one that arrives later. */
export function watchPendingPhoto(onPhoto: (file: File) => void): () => void {
  const check = () => {
    const file = takePendingPhoto();
    if (file) onPhoto(file);
  };
  listeners.add(check);
  check();
  return () => {
    listeners.delete(check);
  };
}
