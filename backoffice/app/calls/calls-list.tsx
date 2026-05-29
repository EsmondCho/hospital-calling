"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useState } from "react";

import { BulkDeleteToolbar } from "@/components/bulk-delete-toolbar";
import { CallStarButton } from "@/components/call-star-button";
import { MobileSelectAllBar } from "@/components/mobile-select-all-bar";
import { PageShell } from "@/components/page-shell";
import { Pagination } from "@/components/pagination";
import { StatusBadge } from "@/components/status-badge";
import { Card } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { callsApi } from "@/lib/api";
import { formatDateTime, formatDuration } from "@/lib/format";
import { usePagePagination } from "@/lib/use-page-pagination";
import { valueOrDash } from "@/lib/timezones";

const INVALIDATE: unknown[][] = [["calls"]];

// DRF page_size for the calls list (PageNumberPagination).
const PAGE_SIZE = 20;

export function CallsList() {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const queryClient = useQueryClient();
  const [selected, setSelected] = useState<Set<number>>(new Set());

  const starred = searchParams.get("starred") === "true";
  const { page, setPage } = usePagePagination();

  const { data, isLoading, isFetching, error } = useQuery({
    queryKey: ["calls", { page, starred }],
    queryFn: () => callsApi.list({ page, starred }),
  });

  const pageCount = Math.max(1, Math.ceil((data?.count ?? 0) / PAGE_SIZE));

  // "Select all on this page" header state.
  const pageCalls = data?.results ?? [];
  const allOnPageSelected =
    pageCalls.length > 0 && pageCalls.every((c) => selected.has(c.id));
  const someOnPageSelected = pageCalls.some((c) => selected.has(c.id));
  const togglePage = () =>
    setSelected((prev) => {
      const next = new Set(prev);
      for (const c of pageCalls) {
        if (allOnPageSelected) next.delete(c.id);
        else next.add(c.id);
      }
      return next;
    });

  // Toggling the starred filter resets paging — drop page and flip the flag in
  // one URL replace.
  const onStarredChange = (next: boolean) => {
    const params = new URLSearchParams(searchParams.toString());
    if (next) params.set("starred", "true");
    else params.delete("starred");
    params.delete("page");
    const query = params.toString();
    router.replace(query ? `${pathname}?${query}` : pathname);
  };

  const bulkDelete = useMutation({
    mutationFn: (ids: number[]) => callsApi.bulkRemove(ids),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["calls"] });
      setSelected(new Set());
    },
  });

  const toggle = (id: number) =>
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });

  return (
    <PageShell
      title="Call logs"
      description="Every BlandAI call we've made. Click for transcript and recording."
    >
      <div className="mb-3 flex items-center gap-2 text-sm">
        <Checkbox
          checked={starred}
          onCheckedChange={(checked) => onStarredChange(checked)}
          aria-label="Starred only"
        />
        <span>Starred only</span>
      </div>
      <BulkDeleteToolbar
        count={selected.size}
        isPending={bulkDelete.isPending}
        resourceName="call"
        onDelete={() => bulkDelete.mutate(Array.from(selected))}
        onClear={() => setSelected(new Set())}
      />
      {/* Mobile card list — hidden at sm+ */}
      <div className="flex flex-col gap-2 sm:hidden">
        {pageCalls.length > 0 && (
          <MobileSelectAllBar
            allSelected={allOnPageSelected}
            someSelected={someOnPageSelected}
            onToggle={togglePage}
          />
        )}
        {isLoading && (
          <p className="text-sm text-muted-foreground">Loading…</p>
        )}
        {error && (
          <p className="text-sm text-destructive">{(error as Error).message}</p>
        )}
        {data?.results.map((c) => (
          <div
            key={c.id}
            className="flex items-start gap-3 rounded-xl bg-card px-3 py-3 ring-1 ring-foreground/10"
            onClick={() => router.push(`/calls/${c.id}`)}
          >
            <div
              className="mt-0.5 shrink-0"
              onClick={(e) => e.stopPropagation()}
            >
              <Checkbox
                checked={selected.has(c.id)}
                onCheckedChange={() => toggle(c.id)}
                aria-label={`Select call ${c.id}`}
              />
            </div>
            <div className="min-w-0 flex-1">
              <div className="flex flex-wrap items-center gap-2">
                <span className="font-mono text-xs text-muted-foreground">#{c.id}</span>
                <StatusBadge value={c.status} />
                {c.duration_seconds != null && (
                  <span className="font-mono text-xs text-muted-foreground">
                    {formatDuration(c.duration_seconds)}
                  </span>
                )}
              </div>
              <div className="mt-1 text-sm font-medium leading-snug">
                {c.hospital_name ? (
                  <Link
                    href={`/hospitals/${c.hospital_id}`}
                    className="text-primary underline"
                    onClick={(e) => e.stopPropagation()}
                  >
                    {c.hospital_name}
                  </Link>
                ) : (
                  <span className="text-muted-foreground">—</span>
                )}
              </div>
              <div className="mt-0.5 flex flex-wrap gap-x-3 gap-y-0.5 text-xs text-muted-foreground">
                <span>{formatDateTime(c.started_at)}</span>
                {c.answered_by ? <span>{c.answered_by}</span> : null}
                <span>💬 {c.comment_count}</span>
              </div>
            </div>
            <div className="shrink-0" onClick={(e) => e.stopPropagation()}>
              <CallStarButton
                id={c.id}
                isStarred={c.is_starred}
                invalidate={INVALIDATE}
              />
            </div>
          </div>
        ))}
        {data && data.results.length === 0 && (
          <p className="text-sm text-muted-foreground">No calls yet.</p>
        )}
      </div>

      {/* Desktop table — hidden below sm */}
      <Card className="hidden sm:flex">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead className="w-10">
                <Checkbox
                  checked={allOnPageSelected}
                  indeterminate={someOnPageSelected && !allOnPageSelected}
                  onCheckedChange={togglePage}
                  disabled={pageCalls.length === 0}
                  aria-label="Select all calls on this page"
                />
              </TableHead>
              <TableHead className="w-10"></TableHead>
              <TableHead>ID</TableHead>
              <TableHead>Status</TableHead>
              <TableHead>Started</TableHead>
              <TableHead>Duration</TableHead>
              <TableHead>Hospital</TableHead>
              <TableHead>Prompt</TableHead>
              <TableHead>Answered by</TableHead>
              <TableHead>Comments</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {isLoading && (
              <TableRow><TableCell colSpan={10} className="text-muted-foreground">Loading…</TableCell></TableRow>
            )}
            {error && (
              <TableRow><TableCell colSpan={10} className="text-destructive">{(error as Error).message}</TableCell></TableRow>
            )}
            {data?.results.map((c) => (
              <TableRow key={c.id} onClick={() => router.push(`/calls/${c.id}`)}>
                <TableCell onClick={(e) => e.stopPropagation()}>
                  <Checkbox
                    checked={selected.has(c.id)}
                    onCheckedChange={() => toggle(c.id)}
                    aria-label={`Select call ${c.id}`}
                  />
                </TableCell>
                <TableCell onClick={(e) => e.stopPropagation()}>
                  <CallStarButton
                    id={c.id}
                    isStarred={c.is_starred}
                    invalidate={INVALIDATE}
                  />
                </TableCell>
                <TableCell className="font-mono text-xs">#{c.id}</TableCell>
                <TableCell><StatusBadge value={c.status} /></TableCell>
                <TableCell>{formatDateTime(c.started_at)}</TableCell>
                <TableCell className="font-mono text-xs">{formatDuration(c.duration_seconds)}</TableCell>
                <TableCell>
                  {c.hospital_name && c.hospital_id != null ? (
                    <Link
                      href={`/hospitals/${c.hospital_id}`}
                      className="text-primary underline"
                      onClick={(e) => e.stopPropagation()}
                    >
                      {c.hospital_name} ↗
                    </Link>
                  ) : (
                    valueOrDash(c.hospital_name)
                  )}
                </TableCell>
                <TableCell>
                  {c.prompt_name && c.prompt_id != null ? (
                    <Link
                      href={`/prompts/${encodeURIComponent(c.prompt_name)}`}
                      className="text-primary underline"
                      onClick={(e) => e.stopPropagation()}
                    >
                      {c.prompt_name} v{c.prompt_version} ↗
                    </Link>
                  ) : (
                    "—"
                  )}
                </TableCell>
                <TableCell>{valueOrDash(c.answered_by)}</TableCell>
                <TableCell className="tabular-nums text-muted-foreground">
                  💬 {c.comment_count}
                </TableCell>
              </TableRow>
            ))}
            {data && data.results.length === 0 && (
              <TableRow><TableCell colSpan={10} className="text-muted-foreground">No calls yet.</TableCell></TableRow>
            )}
          </TableBody>
        </Table>
      </Card>
      <Pagination
        page={page}
        pageCount={pageCount}
        isFetching={isFetching}
        onChange={setPage}
      />
    </PageShell>
  );
}
