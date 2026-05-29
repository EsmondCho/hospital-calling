import { NextResponse, type NextRequest } from "next/server";

import { SESSION_COOKIE, verifySession } from "@/lib/auth/session";

// Routes that must be reachable without a session.
const PUBLIC_PATHS = new Set<string>([
  "/login",
  "/api/login",
  "/api/logout",
]);

export async function middleware(request: NextRequest) {
  const { pathname } = request.nextUrl;

  if (PUBLIC_PATHS.has(pathname)) {
    return NextResponse.next();
  }

  const cookie = request.cookies.get(SESSION_COOKIE)?.value;
  const user = cookie ? await verifySession(cookie) : null;

  if (!user) {
    // JSON 401 for API calls (fetch can react), redirect for page navigations.
    if (pathname.startsWith("/api/")) {
      return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
    }
    const loginUrl = new URL("/login", request.url);
    loginUrl.searchParams.set(
      "next",
      pathname + (request.nextUrl.search || ""),
    );
    return NextResponse.redirect(loginUrl);
  }

  // Identify the authed operator to downstream routes — the proxy forwards
  // this so Django can attribute comments.
  const requestHeaders = new Headers(request.headers);
  requestHeaders.set("x-backoffice-user", user);
  return NextResponse.next({ request: { headers: requestHeaders } });
}

export const config = {
  // Apply everywhere except Next internals and the favicon.
  matcher: ["/((?!_next/static|_next/image|favicon.ico).*)"],
};
