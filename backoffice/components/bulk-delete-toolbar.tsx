"use client";

import { Button } from "@/components/ui/button";

type Props = {
  count: number;
  isPending?: boolean;
  resourceName: string;
  onDelete: () => void;
  onClear: () => void;
};

/**
 * Sticky-feel toolbar shown above a list table when one or more rows are
 * checked. Renders nothing when the selection is empty so the table looks
 * the same as before.
 */
export function BulkDeleteToolbar({
  count,
  isPending,
  resourceName,
  onDelete,
  onClear,
}: Props) {
  if (count === 0) return null;
  return (
    <div className="mb-3 flex flex-wrap items-center gap-2 rounded-md border border-input bg-muted/40 px-3 py-2 text-sm">
      <span className="font-medium">
        {count} {resourceName}
        {count === 1 ? "" : "s"} selected
      </span>
      <div className="ml-auto flex gap-2">
        <Button variant="outline" type="button" onClick={onClear}>
          Clear
        </Button>
        <Button
          type="button"
          disabled={isPending}
          onClick={() => {
            if (
              confirm(
                `Delete ${count} ${resourceName}${count === 1 ? "" : "s"}?`
              )
            ) {
              onDelete();
            }
          }}
        >
          {isPending ? "Deleting…" : "Delete selected"}
        </Button>
      </div>
    </div>
  );
}
