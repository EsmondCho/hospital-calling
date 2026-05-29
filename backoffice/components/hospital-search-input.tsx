"use client";

import { useQuery } from "@tanstack/react-query";
import { useEffect, useMemo, useRef, useState } from "react";

import { hospitalsApi, type Hospital } from "@/lib/api";

const FIELD_CLASS =
  "w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-ring";

type Props = {
  value: Hospital | null;
  onChange: (hospital: Hospital | null) => void;
  placeholder?: string;
  disabled?: boolean;
  /** Optional id for an associated <label htmlFor>. */
  id?: string;
};

export function HospitalSearchInput({
  value,
  onChange,
  placeholder = "Search hospital…",
  disabled,
  id,
}: Props) {
  const [query, setQuery] = useState("");
  const [debounced, setDebounced] = useState("");
  const [open, setOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

  // Debounce keystrokes to keep the API quiet while the user is typing.
  useEffect(() => {
    const t = setTimeout(() => setDebounced(query), 200);
    return () => clearTimeout(t);
  }, [query]);

  // Close the popover when the user clicks outside the component.
  useEffect(() => {
    function onClickOutside(e: MouseEvent) {
      if (
        containerRef.current &&
        !containerRef.current.contains(e.target as Node)
      ) {
        setOpen(false);
      }
    }
    document.addEventListener("mousedown", onClickOutside);
    return () => document.removeEventListener("mousedown", onClickOutside);
  }, []);

  const { data, isFetching } = useQuery({
    queryKey: ["hospitals", "search", debounced],
    queryFn: () => hospitalsApi.list({ q: debounced || undefined }),
    enabled: open,
    staleTime: 30_000,
  });

  const display = useMemo(() => {
    if (value) {
      return `${value.name}${value.state ? ` (${value.state})` : ""}`;
    }
    return query;
  }, [value, query]);

  return (
    <div ref={containerRef} className="relative">
      <input
        id={id}
        className={FIELD_CLASS}
        placeholder={placeholder}
        disabled={disabled}
        value={display}
        onFocus={() => setOpen(true)}
        onChange={(e) => {
          if (value) onChange(null);
          setQuery(e.target.value);
          setOpen(true);
        }}
      />
      {value ? (
        <button
          type="button"
          className="absolute top-1/2 right-2 -translate-y-1/2 rounded px-1 text-xs text-muted-foreground hover:text-foreground"
          onClick={() => {
            onChange(null);
            setQuery("");
          }}
          aria-label="Clear"
        >
          ✕
        </button>
      ) : null}

      {open && !value ? (
        <div className="absolute z-10 mt-1 max-h-64 w-full overflow-y-auto rounded-md border border-input bg-popover shadow-md">
          {isFetching && (
            <div className="px-3 py-2 text-sm text-muted-foreground">
              Searching…
            </div>
          )}
          {!isFetching && data?.results.length === 0 && (
            <div className="px-3 py-2 text-sm text-muted-foreground">
              No matches.
            </div>
          )}
          {data?.results.map((h) => (
            <button
              key={h.id}
              type="button"
              className="block w-full px-3 py-2 text-left text-sm hover:bg-accent"
              onClick={() => {
                onChange(h);
                setQuery("");
                setOpen(false);
              }}
            >
              <div className="flex items-center justify-between gap-2">
                <span className="font-medium">{h.name}</span>
                <span className="shrink-0 text-xs text-muted-foreground">
                  📞 {h.call_attempt_count ?? 0}
                </span>
              </div>
              <div className="text-xs text-muted-foreground">
                {h.city ?? "—"}
                {h.state ? ` · ${h.state}` : ""}
                {h.timezone ? ` · ${h.timezone}` : ""}
              </div>
            </button>
          ))}
        </div>
      ) : null}
    </div>
  );
}
