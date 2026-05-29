"use client";

import { useSearchParams } from "next/navigation";
import { useState, type FormEvent } from "react";

import { Button } from "@/components/ui/button";
import { Field } from "@/components/ui/field";

// Reject open-redirect attempts: only same-origin paths are allowed.
function safeNext(value: string | null): string {
  if (!value) return "/";
  if (!value.startsWith("/") || value.startsWith("//")) return "/";
  return value;
}

export function LoginForm() {
  const search = useSearchParams();
  const next = safeNext(search.get("next"));

  const [user, setUser] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setPending(true);
    try {
      const res = await fetch("/api/login", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ user, password }),
      });
      if (!res.ok) {
        const body = (await res.json().catch(() => ({}))) as { error?: string };
        setError(body.error ?? "Login failed.");
        setPending(false);
        return;
      }
      // Full reload so server components re-render with the new session
      // (router.replace alone keeps the prior RSC payload).
      window.location.href = next;
    } catch {
      setError("Network error. Please try again.");
      setPending(false);
    }
  }

  return (
    <form
      onSubmit={onSubmit}
      className="space-y-4 rounded-lg border bg-card p-6 shadow-sm"
    >
      <Field label="Username" htmlFor="login-user">
        <input
          id="login-user"
          name="username"
          autoComplete="username"
          autoFocus
          value={user}
          onChange={(e) => setUser(e.target.value)}
          required
          className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm outline-none focus:border-ring focus:ring-2 focus:ring-ring/40"
        />
      </Field>
      <Field label="Password" htmlFor="login-pass">
        <input
          id="login-pass"
          name="password"
          type="password"
          autoComplete="current-password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          required
          className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm outline-none focus:border-ring focus:ring-2 focus:ring-ring/40"
        />
      </Field>
      {error ? (
        <p className="text-sm text-destructive" role="alert">
          {error}
        </p>
      ) : null}
      <Button type="submit" disabled={pending} className="w-full">
        {pending ? "Signing in…" : "Sign in"}
      </Button>
      <p className="text-[11px] text-muted-foreground">
        Session lasts 7 days.
      </p>
    </form>
  );
}
