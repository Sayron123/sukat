// Error reporting on the Next.js server (Sentry). Off unless SENTRY_DSN is set.
import * as Sentry from "@sentry/nextjs";

import { DATA_COLLECTION } from "@/lib/sentry-options";
import { scrubEvent } from "@/lib/sentry-scrub";

export function register() {
  const dsn = process.env.SENTRY_DSN;
  if (!dsn) return;
  Sentry.init({
    dsn,
    environment: process.env.APP_ENV ?? "production",
    dataCollection: DATA_COLLECTION, // no users, cookies, headers, bodies or query strings
    tracesSampleRate: 0,
    beforeSend: scrubEvent,
  });
}

// Errors thrown while rendering or in route handlers.
export const onRequestError = Sentry.captureRequestError;
