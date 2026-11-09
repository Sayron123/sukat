import type { DataCollection } from "@sentry/core";

/**
 * What Sentry may collect: nothing about people. Sentry 11 collects users, cookies,
 * headers, bodies and query strings by default, so every category is switched off here
 * (scrubEvent in sentry-scrub.ts then cleans what remains, e.g. emails in messages).
 */
export const DATA_COLLECTION: DataCollection = {
  userInfo: false,
  cookies: false,
  httpHeaders: false,
  httpBodies: [],
  urlQueryParams: false,
  graphQL: { document: false, variables: false },
  genAI: { inputs: false, outputs: false },
  mcp: { inputs: false, outputs: false },
  databaseQueryData: false,
  stackFrameVariables: false, // local variables can hold passwords and tokens
};
