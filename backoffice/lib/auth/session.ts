// HMAC-signed session cookie for the custom login flow. Runs on the Edge
// runtime (middleware), so this uses Web Crypto rather than `node:crypto`.
//
// Cookie format: `<base64url(user)>.<exp>.<base64url(hmac)>`
//   - `exp` is a unix timestamp (seconds) the token is no longer valid.
//   - `hmac` is HMAC-SHA256 of `<base64url(user)>.<exp>` keyed by
//     SESSION_SECRET.

export const SESSION_COOKIE = "bo_session";
export const SESSION_TTL_SECONDS = 60 * 60 * 24 * 7; // 1 week

function getSecret(): string {
  const s = process.env.SESSION_SECRET;
  if (s && s.length >= 16) return s;
  if (process.env.NODE_ENV === "production") {
    throw new Error(
      "SESSION_SECRET must be set (≥16 chars) in production. Add it on Vercel.",
    );
  }
  // Local-dev fallback only. Never used in production (throws above).
  return "dev-only-insecure-secret-do-not-use-in-production";
}

function b64uEncode(bytes: ArrayBuffer | Uint8Array): string {
  const arr = bytes instanceof Uint8Array ? bytes : new Uint8Array(bytes);
  let bin = "";
  for (let i = 0; i < arr.byteLength; i++) bin += String.fromCharCode(arr[i]);
  return btoa(bin).replace(/=+$/, "").replace(/\+/g, "-").replace(/\//g, "_");
}

function b64uEncodeString(s: string): string {
  return b64uEncode(new TextEncoder().encode(s));
}

function b64uDecodeString(s: string): string {
  const std = s.replace(/-/g, "+").replace(/_/g, "/");
  const pad = std.length % 4 === 0 ? "" : "=".repeat(4 - (std.length % 4));
  const bin = atob(std + pad);
  const bytes = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
  return new TextDecoder().decode(bytes);
}

async function hmac(payload: string): Promise<string> {
  const key = await crypto.subtle.importKey(
    "raw",
    new TextEncoder().encode(getSecret()),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign"],
  );
  const sig = await crypto.subtle.sign(
    "HMAC",
    key,
    new TextEncoder().encode(payload),
  );
  return b64uEncode(sig);
}

// Constant-time string compare. Both inputs are base64url HMACs of equal
// length when the cookie is well-formed; the length check still guards the
// general case.
function constantTimeEqual(a: string, b: string): boolean {
  if (a.length !== b.length) return false;
  let diff = 0;
  for (let i = 0; i < a.length; i++) diff |= a.charCodeAt(i) ^ b.charCodeAt(i);
  return diff === 0;
}

export async function signSession(user: string): Promise<string> {
  const exp = Math.floor(Date.now() / 1000) + SESSION_TTL_SECONDS;
  const payload = `${b64uEncodeString(user)}.${exp}`;
  const sig = await hmac(payload);
  return `${payload}.${sig}`;
}

export async function verifySession(cookie: string): Promise<string | null> {
  const parts = cookie.split(".");
  if (parts.length !== 3) return null;
  const [encUser, exp, sig] = parts;
  const expected = await hmac(`${encUser}.${exp}`);
  if (!constantTimeEqual(sig, expected)) return null;
  const expNum = Number(exp);
  if (!Number.isFinite(expNum) || expNum < Math.floor(Date.now() / 1000)) {
    return null;
  }
  try {
    return b64uDecodeString(encUser);
  } catch {
    return null;
  }
}
