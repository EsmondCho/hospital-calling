"use client";

import { Combobox as ComboboxPrimitive } from "@base-ui/react/combobox";
import { ChevronsUpDown } from "lucide-react";
import * as React from "react";

import { cn } from "@/lib/utils";

// A single choice in the dropdown. `value` is the opaque key passed back
// through `onChange`; `label` is the searchable display string; `trailing`
// is an optional node rendered flush-right (e.g. a count badge).
export type ComboboxOption = {
  value: string;
  label: string;
  trailing?: React.ReactNode;
};

// Base UI's combobox auto-derives the display string from a `{ value, label }`
// shape and filters on `label` (case-insensitive substring via Intl.Collator).
// We carry `trailing` along on the same object so the renderer can read it.
type InternalItem = ComboboxOption;

type ComboboxProps = {
  options: ComboboxOption[];
  value: string | null;
  onChange: (value: string | null) => void;
  placeholder?: string;
  searchPlaceholder?: string;
  emptyText?: string;
  disabled?: boolean;
  className?: string;
  /** Optional id for an associated <label htmlFor>. */
  id?: string;
};

const TRIGGER_CLASS =
  "flex h-9 w-full items-center justify-between gap-2 rounded-md border border-input bg-background px-3 py-2 text-sm text-left transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-ring data-[popup-open]:ring-2 data-[popup-open]:ring-ring disabled:cursor-not-allowed disabled:opacity-50";

export function Combobox({
  options,
  value,
  onChange,
  placeholder = "Select…",
  searchPlaceholder = "Search…",
  emptyText = "No results.",
  disabled = false,
  className,
  id,
}: ComboboxProps) {
  const selected = React.useMemo(
    () => options.find((o) => o.value === value) ?? null,
    [options, value],
  );

  return (
    <ComboboxPrimitive.Root<InternalItem>
      items={options}
      value={selected}
      onValueChange={(next) => onChange(next?.value ?? null)}
      disabled={disabled}
    >
      <ComboboxPrimitive.Trigger
        id={id}
        disabled={disabled}
        className={cn(TRIGGER_CLASS, className)}
      >
        <ComboboxPrimitive.Value>
          {(item: InternalItem | null) =>
            item ? (
              <span className="truncate">{item.label}</span>
            ) : (
              <span className="truncate text-muted-foreground">
                {placeholder}
              </span>
            )
          }
        </ComboboxPrimitive.Value>
        <ComboboxPrimitive.Icon className="shrink-0 text-muted-foreground">
          <ChevronsUpDown className="size-4" />
        </ComboboxPrimitive.Icon>
      </ComboboxPrimitive.Trigger>

      <ComboboxPrimitive.Portal>
        <ComboboxPrimitive.Positioner
          sideOffset={4}
          className="z-50 w-[var(--anchor-width)]"
        >
          <ComboboxPrimitive.Popup className="w-full origin-[var(--transform-origin)] overflow-hidden rounded-md border border-border bg-popover text-popover-foreground shadow-md outline-none">
            <div className="border-b border-border p-1">
              <ComboboxPrimitive.Input
                placeholder={searchPlaceholder}
                className="h-8 w-full rounded-sm bg-transparent px-2 text-sm outline-none placeholder:text-muted-foreground"
              />
            </div>
            <ComboboxPrimitive.Empty className="px-3 py-4 text-center text-sm text-muted-foreground">
              {emptyText}
            </ComboboxPrimitive.Empty>
            <ComboboxPrimitive.List className="max-h-60 overflow-y-auto p-1 empty:hidden">
              {(item: InternalItem) => (
                <ComboboxPrimitive.Item
                  key={item.value}
                  value={item}
                  className="flex cursor-pointer items-center justify-between gap-2 rounded-sm px-2 py-1.5 text-sm outline-none select-none data-[highlighted]:bg-accent data-[highlighted]:text-accent-foreground data-[selected]:font-medium"
                >
                  <span className="truncate">{item.label}</span>
                  {item.trailing != null ? (
                    <span className="shrink-0">{item.trailing}</span>
                  ) : null}
                </ComboboxPrimitive.Item>
              )}
            </ComboboxPrimitive.List>
          </ComboboxPrimitive.Popup>
        </ComboboxPrimitive.Positioner>
      </ComboboxPrimitive.Portal>
    </ComboboxPrimitive.Root>
  );
}
