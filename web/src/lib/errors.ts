/** Turn a FastAPI error body into one readable message. Safe on server and client. */
export function errorMessage(body: unknown, fallback: string): string {
  if (typeof body === "object" && body !== null && "detail" in body) {
    const detail = (body as { detail: unknown }).detail;
    if (typeof detail === "string") return detail;
    if (Array.isArray(detail) && detail.length > 0) {
      const first = detail[0] as { loc?: unknown[]; msg?: string };
      const field = Array.isArray(first.loc) ? first.loc.at(-1) : undefined;
      return field ? `${String(field)}: ${first.msg ?? "invalid"}` : (first.msg ?? fallback);
    }
  }
  return fallback;
}
