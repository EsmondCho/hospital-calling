"use client";

import { useQuery } from "@tanstack/react-query";
import { useState } from "react";

import { meApi } from "@/lib/api";

export function UserMenu() {
  const { data } = useQuery({
    queryKey: ["me"],
    queryFn: () => meApi.get(),
    staleTime: 5 * 60_000,
  });
  const [pending, setPending] = useState(false);

  async function signOut() {
    setPending(true);
    try {
      await fetch("/api/logout", { method: "POST" });
    } catch {
      // ignore — we redirect either way
    }
    window.location.href = "/login";
  }

  const user = data?.user;

  return (
    <div className="mt-auto flex flex-col gap-2 border-t border-sidebar-border px-4 py-3 text-xs">
      {user ? (
        <div className="text-muted-foreground">
          Signed in as{" "}
          <span className="font-medium text-foreground">{user}</span>
        </div>
      ) : null}
      <button
        type="button"
        onClick={signOut}
        disabled={pending}
        className="self-start text-left text-muted-foreground hover:text-foreground disabled:opacity-50"
      >
        {pending ? "Signing out…" : "Sign out"}
      </button>
    </div>
  );
}
