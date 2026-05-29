"use client";

import { Button } from "@/components/ui/button";

type Props = {
  count: number;
  isDeleting?: boolean;
  onDelete: () => void;
  onCreateSchedule: () => void;
  onClear: () => void;
};

/**
 * Bulk-action toolbar for the Hospitals list. Shown when ≥1 hospital is
 * checked; offers two actions — delete, or open the schedule-batch modal.
 * Renders nothing when the selection is empty.
 */
export function HospitalBulkToolbar({
  count,
  isDeleting,
  onDelete,
  onCreateSchedule,
  onClear,
}: Props) {
  if (count === 0) return null;

  return (
    <div className="mb-3 flex flex-wrap items-center gap-2 rounded-md border border-input bg-muted/40 px-3 py-2 text-sm">
      <span className="font-medium">
        {count} hospital{count === 1 ? "" : "s"} selected
      </span>
      <div className="ml-auto flex flex-wrap gap-2">
        <Button variant="outline" type="button" onClick={onClear}>
          Clear
        </Button>
        <Button type="button" onClick={onCreateSchedule}>
          Create schedule
        </Button>
        <Button
          variant="outline"
          type="button"
          disabled={isDeleting}
          onClick={() => {
            if (
              confirm(`Delete ${count} hospital${count === 1 ? "" : "s"}?`)
            ) {
              onDelete();
            }
          }}
        >
          {isDeleting ? "Deleting…" : "Delete selected"}
        </Button>
      </div>
    </div>
  );
}
