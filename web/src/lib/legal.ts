/**
 * Shared facts for the Privacy Policy and Terms pages.
 * When the pages change, update LAST_UPDATED here and TERMS_VERSION in
 * api/app/auth/schemas.py (it is saved with each new account).
 */
export const LAST_UPDATED = "9 November 2026";

/** Where people send privacy requests and questions. Set NEXT_PUBLIC_CONTACT_EMAIL. */
export const CONTACT_EMAIL = process.env.NEXT_PUBLIC_CONTACT_EMAIL || "privacy@example.com";
