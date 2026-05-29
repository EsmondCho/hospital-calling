// Operator credentials, sourced from the same env vars the old Basic Auth
// middleware used so existing Vercel config keeps working.
//
// `BASIC_AUTH_USERS` ("user1:pass1,user2:pass2") is the multi-account source.
// As a fallback, a single `BASIC_AUTH_USERNAME`/`BASIC_AUTH_PASSWORD` pair is
// still honored. If neither is configured, the login form accepts any
// non-empty username (local dev — `make dev` works without env setup).
function loadCredentials(): Map<string, string> {
  const creds = new Map<string, string>();

  const multi = process.env.BASIC_AUTH_USERS;
  if (multi) {
    for (const pair of multi.split(",")) {
      const sep = pair.indexOf(":");
      if (sep === -1) continue;
      const u = pair.slice(0, sep).trim();
      const p = pair.slice(sep + 1);
      if (u) creds.set(u, p);
    }
    return creds;
  }

  const u = process.env.BASIC_AUTH_USERNAME;
  const p = process.env.BASIC_AUTH_PASSWORD;
  if (u && p) creds.set(u, p);
  return creds;
}

export function validateCredentials(user: string, password: string): boolean {
  const creds = loadCredentials();
  // No credentials configured → open (local dev parity with the old gate).
  if (creds.size === 0) return user.length > 0;
  return creds.get(user) === password;
}
