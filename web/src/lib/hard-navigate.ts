"use client";

/**
 * Full page load to `path`. Used when the signed-in user changes (login, logout, expired
 * session): Next.js keeps visited pages' React state alive for fast back/forward, so a
 * client-side push could show the previous user's search, data, or role-based buttons.
 * A full load starts from a clean slate.
 */
export function hardNavigate(path: string): void {
  window.location.assign(path);
}
