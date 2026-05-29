import { NextRequest, NextResponse } from "next/server";

/**
 * Reports the currently authenticated operator to the client.
 *
 * Middleware injects `x-backoffice-user` on every authed request; this route
 * reads it back so the comments UI knows which comments belong to the viewer
 * (own-only edit/delete). Returns `{ user: null }` when auth is bypassed
 * (local dev) so the UI degrades gracefully.
 */
export const dynamic = "force-dynamic";

export function GET(request: NextRequest) {
  const user = request.headers.get("x-backoffice-user");
  return NextResponse.json({ user: user ?? null });
}
