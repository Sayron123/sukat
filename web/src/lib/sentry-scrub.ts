import type { ErrorEvent, EventHint } from "@sentry/nextjs";

/**
 * Sentry beforeSend for the web app (browser and server): keep what helps debugging
 * (error, stack, page path, request ID tag), drop anything that can identify a person or
 * hold a secret: headers, cookies, request bodies, query strings, the user, emails and
 * tokens in messages, and breadcrumb data (URLs, form values).
 */
const EMAIL = /[\w.+-]+@[\w-]+\.[\w.-]+/g;
const JWT = /eyJ[\w-]+\.[\w-]+\.[\w-]+/g;
const BEARER = /bearer\s+\S+/gi;

export function scrubText(text: string): string {
  return text.replace(BEARER, "Bearer [removed]").replace(JWT, "[token]").replace(EMAIL, "[email]");
}

export function scrubEvent(event: ErrorEvent, hint?: EventHint): ErrorEvent {
  void hint; // part of Sentry's beforeSend signature; not needed here
  if (event.request) {
    const url = event.request.url?.split("?")[0];
    event.request = { method: event.request.method, url };
  }
  delete event.user;
  delete event.server_name;
  if (event.message) event.message = scrubText(event.message);
  for (const exc of event.exception?.values ?? []) {
    if (exc.value) exc.value = scrubText(exc.value);
  }
  for (const crumb of event.breadcrumbs ?? []) {
    if (crumb.message) crumb.message = scrubText(crumb.message);
    delete crumb.data;
  }
  return event;
}
