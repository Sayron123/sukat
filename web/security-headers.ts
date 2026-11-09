/**
 * Security headers for every page and route of the web app (used by next.config.ts).
 *
 * The Content-Security-Policy limits where the page may load from and connect to:
 * - this site, the API (NEXT_PUBLIC_API_URL, for the health check and local uploads),
 *   Cloudflare R2 (photo uploads go straight to a signed R2 URL) and Sentry (errors).
 * - scripts and styles: this site only. 'unsafe-inline' is still needed for the inline
 *   scripts and styles Next.js writes into each page (nonces would make every page
 *   dynamic). object-src, base-uri, form-action and frame-ancestors are locked down.
 */

function origin(url: string | undefined): string | null {
  if (!url) return null;
  try {
    return new URL(url).origin;
  } catch {
    return null;
  }
}

export function contentSecurityPolicy(env: NodeJS.ProcessEnv, production: boolean): string {
  const connect = [
    "'self'",
    origin(env.NEXT_PUBLIC_API_URL),
    "https://*.r2.cloudflarestorage.com",
    origin(env.NEXT_PUBLIC_SENTRY_DSN), // the ingest host (the key in the DSN is dropped)
  ].filter(Boolean);
  // Next.js dev mode needs eval (fast refresh) and a websocket.
  const script = production ? "'self' 'unsafe-inline'" : "'self' 'unsafe-inline' 'unsafe-eval'";
  if (!production) connect.push("ws:");
  return [
    "default-src 'self'",
    `script-src ${script}`,
    "style-src 'self' 'unsafe-inline'",
    "img-src 'self' blob: data:",
    "font-src 'self'",
    `connect-src ${connect.join(" ")}`,
    "worker-src 'self' blob:",
    "manifest-src 'self'",
    "object-src 'none'",
    "base-uri 'self'",
    "form-action 'self'",
    "frame-ancestors 'none'",
    // No upgrade-insecure-requests: it breaks `next start` over plain HTTP (e.g. testing
    // on a phone over Wi-Fi). HSTS below keeps real visitors on HTTPS.
  ].join("; ");
}

export function securityHeaders(
  env: NodeJS.ProcessEnv = process.env,
  production = process.env.NODE_ENV === "production",
): { key: string; value: string }[] {
  const headers = [
    { key: "Content-Security-Policy", value: contentSecurityPolicy(env, production) },
    { key: "X-Content-Type-Options", value: "nosniff" },
    { key: "X-Frame-Options", value: "DENY" }, // older browsers; CSP frame-ancestors for the rest
    { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
    // The camera is used through a file input (photo of a receipt), which needs no permission.
    {
      key: "Permissions-Policy",
      value: "camera=(), microphone=(), geolocation=(), payment=(), usb=(), interest-cohort=()",
    },
    { key: "Cross-Origin-Opener-Policy", value: "same-origin" },
  ];
  if (production) {
    // HTTPS only for two years. Only sent in production (localhost stays on http).
    headers.push({ key: "Strict-Transport-Security", value: "max-age=63072000; includeSubDomains" });
  }
  return headers;
}
