import * as Sentry from "@sentry/nextjs";

import { DATA_COLLECTION } from "@/lib/sentry-options";
import { scrubEvent } from "@/lib/sentry-scrub";

export function register() {
  const dsn = process.env.SENTRY_DSN;
  if (!dsn) return;
  Sentry.init({
    dsn,
    environment: process.env.APP_ENV ?? "production",
    dataCollection: DATA_COLLECTION,
    tracesSampleRate: 0,
    beforeSend: scrubEvent,
  });
}

export const onRequestError = Sentry.captureRequestError;
