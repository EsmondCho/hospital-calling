import { NextRequest, NextResponse } from "next/server";

/**
 * Server-side proxy for mutating backoffice API calls.
 *
 * The Django backend gates POST/PATCH/PUT/DELETE on `X-Backoffice-Token`.
 * The token lives in the Vercel `BACKOFFICE_API_TOKEN` env var so it never
 * touches the browser bundle; client components hit `/api/proxy/<path>`,
 * this route attaches the header and forwards to `${API_BASE_URL}/<path>`.
 *
 * GET is allowed too so callers don't have to special-case mutation vs read,
 * but most reads still go to the API directly (no token needed for GETs).
 */
const API_BASE_URL =
  process.env.API_BASE_URL ??
  process.env.NEXT_PUBLIC_API_BASE_URL ??
  "http://localhost:8002";

async function handler(
  request: NextRequest,
  { params }: { params: Promise<{ path: string[] }> }
) {
  const { path } = await params;
  // DRF mandates a trailing slash on every collection URL. Next's catch-all
  // route ([...path]) drops it from `params`, so re-append it on the way out
  // — otherwise upstream returns 301 to the slashed URL and the redirect is
  // re-issued as GET, corrupting POST/PATCH/DELETE.
  const target = `${API_BASE_URL}/${path.join("/")}/${request.nextUrl.search}`;

  const token = process.env.BACKOFFICE_API_TOKEN ?? "";
  const headers = new Headers();
  // Forward content-type / accept from the incoming request so binary uploads
  // and JSON both work. Drop hop-by-hop headers (cookies, host).
  const contentType = request.headers.get("content-type");
  if (contentType) headers.set("content-type", contentType);
  headers.set("accept", "application/json");
  if (token) headers.set("x-backoffice-token", token);
  // Forward the authenticated operator (set by middleware) so the Django
  // server can attribute comments to the right account.
  const user = request.headers.get("x-backoffice-user");
  if (user) headers.set("x-backoffice-user", user);

  const body =
    request.method === "GET" || request.method === "HEAD"
      ? undefined
      : await request.arrayBuffer();

  const upstream = await fetch(target, {
    method: request.method,
    headers,
    body,
    cache: "no-store",
  });

  // 204 No Content / 304 Not Modified must have a null body — constructing a
  // Response with any body (even an empty buffer) at these statuses throws,
  // which is why deleting a comment 500'd despite the upstream succeeding.
  if (upstream.status === 204 || upstream.status === 304) {
    return new NextResponse(null, { status: upstream.status });
  }

  const responseBody = await upstream.arrayBuffer();
  return new NextResponse(responseBody, {
    status: upstream.status,
    headers: {
      "content-type":
        upstream.headers.get("content-type") ?? "application/json",
    },
  });
}

export const GET = handler;
export const POST = handler;
export const PUT = handler;
export const PATCH = handler;
export const DELETE = handler;
