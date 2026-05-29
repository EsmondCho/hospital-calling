"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState } from "react";

import { cn } from "@/lib/utils";

import { UserMenu } from "./user-menu";

type NavLeaf = { href: string; label: string };
type NavGroup = { label: string; children: NavLeaf[] };
type NavItem = NavLeaf | NavGroup;

const NAV: NavItem[] = [
  {
    label: "Hospital",
    children: [
      { href: "/hospitals", label: "Hospitals" },
      { href: "/sourcing", label: "Sourcing" },
      { href: "/chain-keywords", label: "Chain keywords" },
    ],
  },
  {
    label: "Call",
    children: [
      { href: "/prompts", label: "Prompts" },
      { href: "/schedules", label: "Schedules" },
      { href: "/calls", label: "Call logs" },
    ],
  },
];

function isGroup(item: NavItem): item is NavGroup {
  return "children" in item;
}

function NavContents({
  onNavigate,
}: {
  onNavigate?: () => void;
}) {
  const pathname = usePathname();

  const isActive = (href: string) =>
    pathname === href || pathname.startsWith(`${href}/`);

  const leafClass = (href: string) =>
    cn(
      "rounded-md px-3 py-2 text-sm font-medium transition-colors",
      isActive(href)
        ? "bg-sidebar-accent text-sidebar-accent-foreground"
        : "text-sidebar-foreground hover:bg-sidebar-accent/60",
    );

  return (
    <>
      <div className="px-4 pt-5 pb-3">
        <div className="text-xs font-medium tracking-wide text-muted-foreground uppercase">
          HOSPCALL
        </div>
        <div className="text-base font-semibold">Backoffice</div>
      </div>
      <nav className="flex flex-col gap-0.5 p-2">
        {NAV.map((item) =>
          isGroup(item) ? (
            <div key={item.label} className="mt-1 first:mt-0">
              <div className="px-3 pt-2 pb-1 text-[11px] font-semibold tracking-wide text-muted-foreground uppercase">
                {item.label}
              </div>
              <div className="flex flex-col gap-0.5">
                {item.children.map((child) => (
                  <Link
                    key={child.href}
                    href={child.href}
                    className={cn(leafClass(child.href), "ml-2")}
                    onClick={onNavigate}
                  >
                    {child.label}
                  </Link>
                ))}
              </div>
            </div>
          ) : (
            <Link
              key={item.href}
              href={item.href}
              className={leafClass(item.href)}
              onClick={onNavigate}
            >
              {item.label}
            </Link>
          ),
        )}
      </nav>
      <UserMenu />
      <div className="px-4 pt-2 pb-4 text-[11px] text-muted-foreground">
        automated vet-clinic outreach
      </div>
    </>
  );
}

export function Sidebar() {
  const [drawerOpen, setDrawerOpen] = useState(false);

  return (
    <>
      {/* Mobile top bar — hidden on sm+ */}
      <header className="flex h-12 shrink-0 items-center gap-3 border-b bg-sidebar px-3 sm:hidden">
        <button
          type="button"
          aria-label="Open navigation"
          aria-expanded={drawerOpen}
          onClick={() => setDrawerOpen(true)}
          className="flex size-9 items-center justify-center rounded-md text-sidebar-foreground hover:bg-sidebar-accent/60"
        >
          {/* Hamburger icon */}
          <svg
            viewBox="0 0 16 16"
            fill="currentColor"
            className="size-5"
            aria-hidden="true"
          >
            <path d="M1 3h14v1.5H1zm0 4.25h14v1.5H1zm0 4.25h14v1.5H1z" />
          </svg>
        </button>
        <span className="text-sm font-semibold text-sidebar-foreground">
          HOSPCALL Backoffice
        </span>
      </header>

      {/* Mobile drawer backdrop */}
      {drawerOpen && (
        <div
          className="fixed inset-0 z-40 bg-black/40 sm:hidden"
          onClick={() => setDrawerOpen(false)}
          aria-hidden="true"
        />
      )}

      {/* Mobile drawer panel */}
      <aside
        className={cn(
          "fixed inset-y-0 left-0 z-50 flex w-64 flex-col border-r bg-sidebar text-sidebar-foreground transition-transform duration-200 sm:hidden",
          drawerOpen ? "translate-x-0" : "-translate-x-full",
        )}
        aria-label="Navigation"
      >
        <div className="flex items-center justify-end px-3 pt-3">
          <button
            type="button"
            aria-label="Close navigation"
            onClick={() => setDrawerOpen(false)}
            className="flex size-8 items-center justify-center rounded-md text-sidebar-foreground hover:bg-sidebar-accent/60"
          >
            <svg viewBox="0 0 16 16" fill="currentColor" className="size-4" aria-hidden="true">
              <path d="M3.72 3.72a.75.75 0 0 1 1.06 0L8 6.94l3.22-3.22a.75.75 0 1 1 1.06 1.06L9.06 8l3.22 3.22a.75.75 0 1 1-1.06 1.06L8 9.06l-3.22 3.22a.75.75 0 0 1-1.06-1.06L6.94 8 3.72 4.78a.75.75 0 0 1 0-1.06z" />
            </svg>
          </button>
        </div>
        <NavContents onNavigate={() => setDrawerOpen(false)} />
      </aside>

      {/* Desktop left rail — hidden below sm. `sticky top-0 h-screen` keeps the
          rail covering the full viewport height (and visible) as the page body
          scrolls; without it the background ended at one viewport height and
          white showed below the rail on long, scrolled pages. */}
      <aside className="sticky top-0 hidden h-screen w-56 shrink-0 flex-col overflow-y-auto border-r bg-sidebar text-sidebar-foreground sm:flex">
        <NavContents />
      </aside>
    </>
  );
}
