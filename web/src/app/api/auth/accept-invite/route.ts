import type { NextRequest } from "next/server";

import { forwardAuth } from "@/lib/server/auth-route";

export async function POST(req: NextRequest) {
  return forwardAuth(req, "/staff/invites/accept");
}
