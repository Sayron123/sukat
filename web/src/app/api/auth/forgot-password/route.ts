import type { NextRequest } from "next/server";

import { forwardPublic } from "@/lib/server/auth-route";

export async function POST(req: NextRequest) {
  return forwardPublic(req, "/auth/forgot-password");
}
