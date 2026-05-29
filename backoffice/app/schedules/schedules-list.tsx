"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { BulkDeleteToolbar } from "@/components/bulk-delete-toolbar";
import { MobileSelectAllBar } from "@/components/mobile-select-all-bar";
import { NewScheduleForm } from "@/components/new-schedule-form";
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
import { schedulesApi, type CallSchedule } from "@/lib/api";
import { usePagePagination } from "@/lib/use-page-pagination";
import { KST, formatInTimezone, valueOrDash } from "@/lib/timezones";

// DRF page_size for the schedules list (PageNumberPagination).
const PAGE_SIZE = 20;

// Label for a schedule's hospital column: the single hospital name when it
// dials exactly one, otherwise an "N hospitals" count.
function hospitalsLabel(s: CallSchedule): string {
  if (s.hospital_count === 1) {
    return s.targets[0]?.hospital_name ?? "1 hospital";
  }
  return `${s.hospital_count} hospitals`;
}

export function SchedulesList() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const [selected, setSelected] = useState<Set<number>>(new Set());

  const { page, setPage } = usePagePagination();
  const list = useQuery({
    queryKey: ["schedules", { page }],
    queryFn: () => schedulesApi.list({ page }),
  });
  const pageCount = Math.max(1, Math.ceil((list.data?.count ?? 0) / PAGE_SIZE));

  const rows = list.data?.results ?? [];

  // "Select all on this page" header state.
  const allOnPageSelected =
    rows.length > 0 && rows.every((s) => selected.has(s.id));
  const someOnPageSelected = rows.some((s) => selected.has(s.id));
  const togglePage = () =>
    setSelected((prev) => {
      const next = new Set(prev);
      for (const s of rows) {
        if (allOnPageSelected) next.delete(s.id);
        else next.add(s.id);
      }
      return next;
    });

  const bulkDelete = useMutation({
    mutationFn: (ids: number[]) => schedulesApi.bulkRemove(ids),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["schedules"] });
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
      title="Schedules"
      description="Planned outbound calls. The Celery beat task picks PENDING rows whose scheduled_at has passed."
    >
      <NewScheduleForm />
      <BulkDeleteToolbar
        count={selected.size}
        isPending={bulkDelete.isPending}
        resourceName="schedule"
        onDelete={() => bulkDelete.mutate(Array.from(selected))}
        onClear={() => setSelected(new Set())}
      />
      {/* Mobile card list — hidden at sm+ */}
      <div className="flex flex-col gap-2 sm:hidden">
        {rows.length > 0 && (
          <MobileSelectAllBar
            allSelected={allOnPageSelected}
            someSelected={someOnPageSelected}
            onToggle={togglePage}
          />
        )}
        {list.isLoading && (
          <p className="text-sm text-muted-foreground">Loading…</p>
        )}
        {list.error && (
          <p className="text-sm text-destructive">
            {(list.error as Error).message}
          </p>
        )}
        {rows.map((s) => (
          <div
            key={s.id}
            className="flex items-start gap-3 rounded-xl bg-card px-3 py-3 ring-1 ring-foreground/10"
            onClick={() => router.push(`/schedules/${s.id}`)}
          >
            <div
              className="mt-0.5 shrink-0"
              onClick={(e) => e.stopPropagation()}
            >
              <Checkbox
                checked={selected.has(s.id)}
                onCheckedChange={() => toggle(s.id)}
                aria-label={`Select schedule ${s.id}`}
              />
            </div>
            <div className="min-w-0 flex-1">
              <div className="flex flex-wrap items-center gap-2">
                <span className="font-mono text-xs text-muted-foreground">#{s.id}</span>
                <StatusBadge value={s.status} />
              </div>
              <div className="mt-1 text-sm font-medium leading-snug">
                {hospitalsLabel(s)}
              </div>
              <div className="mt-0.5 font-mono text-xs text-muted-foreground">
                {formatInTimezone(s.scheduled_at, KST)} KST
              </div>
            </div>
          </div>
        ))}
        {list.data && rows.length === 0 && (
          <p className="text-sm text-muted-foreground">No schedules yet.</p>
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
                  disabled={rows.length === 0}
                  aria-label="Select all schedules on this page"
                />
              </TableHead>
              <TableHead>ID</TableHead>
              <TableHead>Status</TableHead>
              <TableHead>KST</TableHead>
              <TableHead>Hospital local</TableHead>
              <TableHead>Hospitals</TableHead>
              <TableHead>Prompt</TableHead>
              <TableHead>Voice</TableHead>
              <TableHead>Model</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {list.isLoading && (
              <TableRow><TableCell colSpan={9} className="text-muted-foreground">Loading…</TableCell></TableRow>
            )}
            {list.error && (
              <TableRow><TableCell colSpan={9} className="text-destructive">{(list.error as Error).message}</TableCell></TableRow>
            )}
            {rows.map((s) => {
              const tz = s.targets[0]?.hospital_timezone ?? null;
              return (
                <TableRow key={s.id} onClick={() => router.push(`/schedules/${s.id}`)}>
                  <TableCell onClick={(e) => e.stopPropagation()}>
                    <Checkbox
                      checked={selected.has(s.id)}
                      onCheckedChange={() => toggle(s.id)}
                      aria-label={`Select schedule ${s.id}`}
                    />
                  </TableCell>
                  <TableCell className="font-mono text-xs">#{s.id}</TableCell>
                  <TableCell><StatusBadge value={s.status} /></TableCell>
                  <TableCell className="font-mono text-xs">
                    {formatInTimezone(s.scheduled_at, KST)}
                  </TableCell>
                  <TableCell className="font-mono text-xs">
                    {tz ? (
                      <>
                        {formatInTimezone(s.scheduled_at, tz)}
                        <span className="ml-1 text-muted-foreground">{tz}</span>
                      </>
                    ) : (
                      "—"
                    )}
                  </TableCell>
                  <TableCell>{hospitalsLabel(s)}</TableCell>
                  <TableCell>
                    {s.prompt_name && s.prompt_id != null ? (
                      <span>
                        {s.prompt_name} v{s.prompt_version}
                      </span>
                    ) : (
                      "—"
                    )}
                  </TableCell>
                  <TableCell>
                    {s.voice === "random" ? "Random" : valueOrDash(s.voice)}
                  </TableCell>
                  <TableCell>{valueOrDash(s.model)}</TableCell>
                </TableRow>
              );
            })}
            {list.data && rows.length === 0 && (
              <TableRow><TableCell colSpan={9} className="text-muted-foreground">
                No schedules yet.
              </TableCell></TableRow>
            )}
          </TableBody>
        </Table>
      </Card>
      <Pagination
        page={page}
        pageCount={pageCount}
        isFetching={list.isFetching}
        onChange={setPage}
      />
    </PageShell>
  );
}
