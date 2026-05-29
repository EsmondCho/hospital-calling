"use client";

import { Check, Minus } from "lucide-react";

import { cn } from "@/lib/utils";

type Props = {
  allSelected: boolean;
  someSelected: boolean;
  onToggle: () => void;
};

/**
 * Mobile-only "select all on this page" button. Desktop list tables have a
 * header checkbox for this; the mobile card lists have no header, so this bar
 * gives the same page-level select / deselect. Hidden at sm+ (`sm:hidden`).
 *
 * The whole row is the tap target (a single <button>), with a styled box
 * showing checked / indeterminate state. We render a plain styled box rather
 * than the interactive <Checkbox> because a checkbox button can't be nested
 * inside this button (invalid HTML).
 */
export function MobileSelectAllBar({ allSelected, someSelected, onToggle }: Props) {
  const indeterminate = someSelected && !allSelected;
  return (
    <button
      type="button"
      onClick={onToggle}
      className="flex w-full items-center gap-2 rounded-xl bg-card px-3 py-2.5 text-left text-sm font-medium ring-1 ring-foreground/10 sm:hidden"
    >
      <span
        data-checked={allSelected || undefined}
        data-indeterminate={indeterminate || undefined}
        className={cn(
          "flex size-5 shrink-0 items-center justify-center rounded-[5px] border border-input bg-background text-primary-foreground transition-colors",
          "data-[checked]:border-primary data-[checked]:bg-primary",
          "data-[indeterminate]:border-primary data-[indeterminate]:bg-primary",
        )}
      >
        {allSelected ? (
          <Check className="size-3.5" strokeWidth={3} />
        ) : indeterminate ? (
          <Minus className="size-3.5" strokeWidth={3} />
        ) : null}
      </span>
      {allSelected ? "Deselect all on this page" : "Select all on this page"}
    </button>
  );
}
