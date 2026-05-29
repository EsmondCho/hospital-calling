import { NextRequest, NextResponse } from "next/server";

import { validateCredentials } from "@/lib/auth/credentials";
import {
  SESSION_COOKIE,
  SESSION_TTL_SECONDS,
  signSession,
} from "@/lib/auth/session";

export const runtime = "edge";

export async function POST(request: NextRequest) {
  const body = (await request.json().catch(() => null)) as
    | { user?: unknown; password?: unknown }
    | null;
  const user =
    typeof body?.user === "string" ? body.user.trim() : "";
  const password =
    typeof body?.password === "string" ? body.password : "";

  if (!user || !password) {
    return NextResponse.json(
      { error: "Username and password are required." },
      { status: 400 },
    );
  }

  if (!validateCredentials(user, password)) {
    return NextResponse.json(
      { error: "Invalid username or password." },
      { status: 401 },
    );
  }

  const token = await signSession(user);
  const res = NextResponse.json({ ok: true, user });
  res.cookies.set(SESSION_COOKIE, token, {
    httpOnly: true,
    sameSite: "lax",
    secure: process.env.NODE_ENV === "production",
    path: "/",
    maxAge: SESSION_TTL_SECONDS,
  });
  return res;
}
