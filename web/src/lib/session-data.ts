/**
 * Data this browser tab keeps for the signed-in person: the AI chat, and the ids of
 * scan saves in progress (sessionStorage). Cleared when someone signs in or out, so the
 * next person on a shared phone never sees the previous person's chat (which can hold
 * manager-only numbers) or reuses their save ids.
 */
export function clearSessionData(): void {
  try {
    sessionStorage.clear();
  } catch {
    // storage blocked (private mode): nothing was kept
  }
}
