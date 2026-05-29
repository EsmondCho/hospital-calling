"use client";

import { usePathname } from "next/navigation";
import type { ReactNode } from "react";

import { Sidebar } from "./sidebar";

// Hides the operator chrome on the login page (no sidebar, full-bleed shell).
// Anything else renders the standard sidebar + main layout.
export function AppShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  if (pathname === "/login") {
    return <>{children}</>;
  }
  return (
    <div className="flex min-h-screen flex-col sm:flex-row">
      <Sidebar />
      <main className="min-w-0 flex-1 overflow-auto">{children}</main>
    </div>
  );
}
