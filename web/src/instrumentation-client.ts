// Error reporting in the browser (Sentry). Off unless NEXT_PUBLIC_SENTRY_DSN is set.
import * as Sentry from "@sentry/nextjs";

import { DATA_COLLECTION } from "@/lib/sentry-options";
import { scrubEvent } from "@/lib/sentry-scrub";

const dsn = process.env.NEXT_PUBLIC_SENTRY_DSN;

if (dsn) {
  Sentry.init({
    dsn,
    environment: process.env.NEXT_PUBLIC_APP_ENV ?? "production",
    dataCollection: DATA_COLLECTION, // no users, cookies, headers, bodies or query strings
    tracesSampleRate: 0, // errors only
    beforeSend: scrubEvent,
  });
}
