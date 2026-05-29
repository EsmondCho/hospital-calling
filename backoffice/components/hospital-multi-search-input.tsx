"use client";

import { useQuery } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";

import { hospitalsApi, type Hospital } from "@/lib/api";

const FIELD_CLASS =
  "w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-ring";

type Props = {
  value: Hospital[];
  onChange: (hospitals: Hospital[]) => void;
  placeholder?: string;
  disabled?: boolean;
};

/**
 * Multi-select hospital search. The selected list is kept as an ordered
 * array — the order IS the call dispatch order — and rendered as numbered
 * chips. The dropdown stays open after a pick so the operator can keep
 * adding hospitals in one pass.
 */
export function HospitalMultiSearchInput({
  value,
  onChange,
  placeholder = "Search hospital…",
  disabled,
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

  const selectedIds = new Set(value.map((h) => h.id));

  const add = (h: Hospital) => {
    if (selectedIds.has(h.id)) return;
    onChange([...value, h]);
    setQuery("");
  };

  const remove = (id: number) => {
    onChange(value.filter((h) => h.id !== id));
  };

  return (
    <div ref={containerRef} className="space-y-2">
      <div className="relative">
        <input
          className={FIELD_CLASS}
          placeholder={placeholder}
          disabled={disabled}
          value={query}
          onFocus={() => setOpen(true)}
          onChange={(e) => {
            setQuery(e.target.value);
            setOpen(true);
          }}
        />

        {open ? (
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
            {data?.results.map((h) => {
              const picked = selectedIds.has(h.id);
              return (
                <button
                  key={h.id}
                  type="button"
                  disabled={picked}
                  className="block w-full px-3 py-2 text-left text-sm hover:bg-accent disabled:cursor-not-allowed disabled:opacity-50"
                  onClick={() => add(h)}
                >
                  <div className="flex items-center justify-between gap-2">
                    <span className="font-medium">
                      {h.name}
                      {picked ? " ✓" : ""}
                    </span>
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
              );
            })}
          </div>
        ) : null}
      </div>

      {value.length > 0 ? (
        <ol className="space-y-1">
          {value.map((h, i) => (
            <li
              key={h.id}
              className="flex items-center gap-2 rounded-md border border-input bg-background px-2 py-1 text-sm"
            >
              <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-muted text-xs font-medium text-muted-foreground">
                {i + 1}
              </span>
              <span className="min-w-0 flex-1 truncate">
                {h.name}
                {h.state ? (
                  <span className="text-muted-foreground"> ({h.state})</span>
                ) : null}
              </span>
              <button
                type="button"
                disabled={disabled}
                className="shrink-0 rounded px-1 text-xs text-muted-foreground hover:text-foreground"
                onClick={() => remove(h.id)}
                aria-label={`Remove ${h.name}`}
              >
                ✕
              </button>
            </li>
          ))}
        </ol>
      ) : null}
    </div>
  );
}
