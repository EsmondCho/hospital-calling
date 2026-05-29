"use client";

import { Button } from "@/components/ui/button";

type Props = {
  /** 1-based current page. */
  page: number;
  /** Total number of pages (≥ 1). */
  pageCount: number;
  onChange: (page: number) => void;
  isFetching?: boolean;
};

// How many numbered buttons to show around the current page before collapsing
// the rest into an ellipsis. Always shows first + last page.
const SIBLINGS = 1;

// Build the list of page numbers / ellipsis markers to render. `"…"` is a
// gap; numbers are clickable pages. First and last pages always appear.
function buildPages(page: number, pageCount: number): Array<number | "…"> {
  if (pageCount <= 7) {
    return Array.from({ length: pageCount }, (_, i) => i + 1);
  }

  const pages: Array<number | "…"> = [1];
  const start = Math.max(2, page - SIBLINGS);
  const end = Math.min(pageCount - 1, page + SIBLINGS);

  if (start > 2) pages.push("…");
  for (let p = start; p <= end; p++) pages.push(p);
  if (end < pageCount - 1) pages.push("…");

  pages.push(pageCount);
  return pages;
}

/**
 * Numbered pager: « Prev  1 2 3 … N  Next ». The current page is highlighted,
 * prev/next disable at the ends, and a leading ellipsis collapses long ranges.
 */
export function Pagination({ page, pageCount, onChange, isFetching }: Props) {
  if (pageCount <= 1) return null;

  const go = (next: number) => {
    const clamped = Math.min(pageCount, Math.max(1, next));
    if (clamped !== page) onChange(clamped);
  };

  return (
    <div className="mt-3 flex flex-wrap items-center justify-end gap-1.5 text-sm">
      <Button
        variant="outline"
        size="sm"
        type="button"
        disabled={page <= 1 || isFetching}
        onClick={() => go(page - 1)}
      >
        « Prev
      </Button>
      {buildPages(page, pageCount).map((p, i) =>
        p === "…" ? (
          <span
            key={`ellipsis-${i}`}
            className="px-1.5 text-muted-foreground select-none"
          >
            …
          </span>
        ) : (
          <Button
            key={p}
            variant={p === page ? "default" : "outline"}
            size="sm"
            type="button"
            aria-current={p === page ? "page" : undefined}
            disabled={isFetching}
            onClick={() => go(p)}
          >
            {p}
          </Button>
        )
      )}
      <Button
        variant="outline"
        size="sm"
        type="button"
        disabled={page >= pageCount || isFetching}
        onClick={() => go(page + 1)}
      >
        Next »
      </Button>
    </div>
  );
}
