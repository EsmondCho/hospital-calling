"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useState } from "react";

import { HospitalBulkToolbar } from "@/components/hospital-bulk-toolbar";
import { HospitalScheduleModal } from "@/components/hospital-schedule-modal";
import { MobileSelectAllBar } from "@/components/mobile-select-all-bar";
import { NewHospitalForm } from "@/components/new-hospital-form";
import { PageShell } from "@/components/page-shell";
import { Pagination } from "@/components/pagination";
import { ServiceTagsChips } from "@/components/service-tags-chips";
import { StatusBadge } from "@/components/status-badge";
import { Card } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Combobox, type ComboboxOption } from "@/components/ui/combobox";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { hospitalsApi } from "@/lib/api";
import { valueOrDash } from "@/lib/timezones";

import { useHospitalSelection } from "./selection-context";

const COL_COUNT = 9;

// DRF page_size for the hospitals list (PageNumberPagination).
const PAGE_SIZE = 20;

// Ownership filter options — mirror hospital/vars.py HospitalOwnership.
const OWNERSHIP_OPTIONS: ComboboxOption[] = [
  { value: "", label: "All ownership" },
  ...[
    "INDEPENDENT",
    "CHAIN",
    "MARS_VH",
    "RETAIL_EMBEDDED",
    "NONPROFIT",
    "UNIVERSITY",
    "FRANCHISE",
    "UNCLASSIFIED",
  ].map((v) => ({ value: v, label: v })),
];

export function HospitalsList() {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const queryClient = useQueryClient();
  // Multi-select lives in a context mounted by `app/hospitals/layout.tsx`, so
  // it survives navigating into a hospital's detail page and back.
  const { selected, picked, toggle, setMany, clear } = useHospitalSelection();
  const [scheduleOpen, setScheduleOpen] = useState(false);

  // Filter + pagination state lives in the URL so it survives navigation to a
  // detail page and back. `ownership` is the filter, `page` the 1-based page
  // number used both for fetching and the running idx column.
  const ownership = searchParams.get("ownership") ?? "";
  const page = Math.max(1, Number(searchParams.get("page")) || 1);

  // Replace (not push) so back/forward history isn't polluted with each
  // filter/page tweak.
  const updateParams = (next: { ownership?: string; page?: number }) => {
    const params = new URLSearchParams(searchParams.toString());
    const ownershipNext = next.ownership ?? ownership;
    const pageNext = next.page ?? page;

    if (ownershipNext) params.set("ownership", ownershipNext);
    else params.delete("ownership");

    if (pageNext > 1) params.set("page", String(pageNext));
    else params.delete("page");

    const query = params.toString();
    router.replace(query ? `${pathname}?${query}` : pathname);
  };

  const { data, isLoading, isFetching, error } = useQuery({
    queryKey: ["hospitals", { ownership, page }],
    queryFn: () =>
      hospitalsApi.list({
        ownership: ownership || undefined,
        page,
      }),
  });

  const pageCount = Math.max(1, Math.ceil((data?.count ?? 0) / PAGE_SIZE));

  const bulkDelete = useMutation({
    mutationFn: (ids: number[]) => hospitalsApi.bulkRemove(ids),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["hospitals"] });
      clear();
    },
  });

  // Filter change resets to the first page.
  const onOwnershipChange = (next: string | null) => {
    updateParams({ ownership: next ?? "", page: 1 });
  };

  const pickedHospitals = Array.from(picked.values());

  // "Select all on this page" header state.
  const pageHospitals = data?.results ?? [];
  const allOnPageSelected =
    pageHospitals.length > 0 && pageHospitals.every((h) => selected.has(h.id));
  const someOnPageSelected = pageHospitals.some((h) => selected.has(h.id));

  return (
    <PageShell
      title="Hospitals"
      description="US vet hospitals tracked by HOSPCALL. Only INDEPENDENT hospitals are call candidates."
    >
      <NewHospitalForm />
      <div className="mb-3 w-full max-w-xs">
        <Combobox
          options={OWNERSHIP_OPTIONS}
          value={ownership}
          onChange={onOwnershipChange}
          placeholder="All ownership"
          searchPlaceholder="Filter ownership…"
        />
      </div>
      <HospitalBulkToolbar
        count={selected.size}
        isDeleting={bulkDelete.isPending}
        onDelete={() => bulkDelete.mutate(Array.from(selected))}
        onCreateSchedule={() => setScheduleOpen(true)}
        onClear={clear}
      />
      {/* Mobile card list — hidden at sm+ */}
      <div className="flex flex-col gap-2 sm:hidden">
        {pageHospitals.length > 0 && (
          <MobileSelectAllBar
            allSelected={allOnPageSelected}
            someSelected={someOnPageSelected}
            onToggle={() => setMany(pageHospitals, !allOnPageSelected)}
          />
        )}
        {isLoading && (
          <p className="text-sm text-muted-foreground">Loading…</p>
        )}
        {error && (
          <p className="text-sm text-destructive">{(error as Error).message}</p>
        )}
        {data?.results.map((h) => (
          <div
            key={h.id}
            className="flex items-start gap-3 rounded-xl bg-card px-3 py-3 ring-1 ring-foreground/10"
            onClick={() => router.push(`/hospitals/${h.id}`)}
          >
            <div
              className="mt-0.5 shrink-0"
              onClick={(e) => e.stopPropagation()}
            >
              <Checkbox
                checked={selected.has(h.id)}
                onCheckedChange={() => toggle(h)}
                aria-label={`Select hospital ${h.id}`}
              />
            </div>
            <div className="min-w-0 flex-1">
              <div className="flex flex-wrap items-center gap-2">
                <span className="font-medium text-sm leading-snug">{h.name}</span>
                <StatusBadge value={h.ownership} />
              </div>
              <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-0.5 text-xs text-muted-foreground">
                {h.city || h.state ? (
                  <span>{[h.city, h.state].filter(Boolean).join(", ")}</span>
                ) : null}
                {h.phone_e164 ? (
                  <span className="font-mono">{h.phone_e164}</span>
                ) : null}
                <span>{h.call_attempt_count ?? 0} calls</span>
              </div>
              {h.service_tags && h.service_tags.length > 0 ? (
                <div className="mt-1.5">
                  <ServiceTagsChips tags={h.service_tags} />
                </div>
              ) : null}
            </div>
            <span className="shrink-0 font-mono text-[11px] text-muted-foreground">
              #{h.id}
            </span>
          </div>
        ))}
        {data && data.results.length === 0 && (
          <p className="text-sm text-muted-foreground">No hospitals yet.</p>
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
                  onCheckedChange={() => setMany(pageHospitals, !allOnPageSelected)}
                  disabled={pageHospitals.length === 0}
                  aria-label="Select all hospitals on this page"
                />
              </TableHead>
              <TableHead>ID</TableHead>
              <TableHead>Name</TableHead>
              <TableHead>Ownership</TableHead>
              <TableHead>Service tags</TableHead>
              <TableHead>City</TableHead>
              <TableHead>State</TableHead>
              <TableHead>Phone</TableHead>
              <TableHead>Calls</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {isLoading && (
              <TableRow>
                <TableCell colSpan={COL_COUNT} className="text-muted-foreground">
                  Loading…
                </TableCell>
              </TableRow>
            )}
            {error && (
              <TableRow>
                <TableCell colSpan={COL_COUNT} className="text-destructive">
                  {(error as Error).message}
                </TableCell>
              </TableRow>
            )}
            {data?.results.map((h) => (
              <TableRow
                key={h.id}
                onClick={() => router.push(`/hospitals/${h.id}`)}
              >
                <TableCell onClick={(e) => e.stopPropagation()}>
                  <Checkbox
                    checked={selected.has(h.id)}
                    onCheckedChange={() => toggle(h)}
                    aria-label={`Select hospital ${h.id}`}
                  />
                </TableCell>
                <TableCell className="font-mono text-xs">#{h.id}</TableCell>
                <TableCell className="font-medium">{h.name}</TableCell>
                <TableCell>
                  <StatusBadge value={h.ownership} />
                </TableCell>
                <TableCell>
                  <ServiceTagsChips tags={h.service_tags} />
                </TableCell>
                <TableCell>{valueOrDash(h.city)}</TableCell>
                <TableCell>{valueOrDash(h.state)}</TableCell>
                <TableCell className="font-mono text-xs">
                  {valueOrDash(h.phone_e164)}
                </TableCell>
                <TableCell className="font-mono text-xs">
                  {h.call_attempt_count ?? 0}
                </TableCell>
              </TableRow>
            ))}
            {data && data.results.length === 0 && (
              <TableRow>
                <TableCell colSpan={COL_COUNT} className="text-muted-foreground">
                  No hospitals yet.
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </Card>
      <Pagination
        page={page}
        pageCount={pageCount}
        isFetching={isFetching}
        onChange={(p) => updateParams({ page: p })}
      />
      <HospitalScheduleModal
        open={scheduleOpen}
        onOpenChange={setScheduleOpen}
        hospitals={pickedHospitals}
        onCreated={() => {
          // Selection consumed — drop it and jump to the Schedules page so
          // the operator sees the batch they just created.
          clear();
          router.push("/schedules");
        }}
      />
    </PageShell>
  );
}
