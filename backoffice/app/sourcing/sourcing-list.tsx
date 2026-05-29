"use client";

import { useQuery } from "@tanstack/react-query";
import { useRouter } from "next/navigation";

import { NewSourcingJobForm } from "@/components/new-sourcing-job-form";
import { PageShell } from "@/components/page-shell";
import { Pagination } from "@/components/pagination";
import { PartialBadge, StatusBadge } from "@/components/status-badge";
import { Card } from "@/components/ui/card";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { sourcingApi } from "@/lib/api";
import { formatDateTime } from "@/lib/format";
import { usePagePagination } from "@/lib/use-page-pagination";

// DRF page_size for the sourcing-jobs list (PageNumberPagination).
const PAGE_SIZE = 20;

export function SourcingList() {
  const router = useRouter();
  const { page, setPage } = usePagePagination();
  const { data, isLoading, isFetching, error } = useQuery({
    queryKey: ["sourcing-jobs", { page }],
    queryFn: () => sourcingApi.list({ page }),
    // Auto-refresh while there are active jobs — the list page is where
    // operators land after triggering, so they expect fresh counters.
    refetchInterval: 5_000,
  });
  const pageCount = Math.max(1, Math.ceil((data?.count ?? 0) / PAGE_SIZE));

  return (
    <PageShell
      title="Sourcing"
      description="Trigger Google Places + LLM hospital sourcing for a US city."
    >
      <NewSourcingJobForm />
      <Card>
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Created</TableHead>
              <TableHead>Region</TableHead>
              <TableHead>Status</TableHead>
              <TableHead className="text-right">Tiles</TableHead>
              <TableHead className="text-right">Fetched</TableHead>
              <TableHead className="text-right">Inserted</TableHead>
              <TableHead className="text-right">Updated</TableHead>
              <TableHead className="text-right">Review</TableHead>
              <TableHead className="text-right">Cost</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {isLoading && (
              <TableRow>
                <TableCell colSpan={9} className="text-muted-foreground">
                  Loading…
                </TableCell>
              </TableRow>
            )}
            {error && (
              <TableRow>
                <TableCell colSpan={9} className="text-destructive">
                  {(error as Error).message}
                </TableCell>
              </TableRow>
            )}
            {data?.results.map((j) => (
              <TableRow
                key={j.id}
                onClick={() => router.push(`/sourcing/${j.id}`)}
              >
                <TableCell className="text-xs">
                  {formatDateTime(j.created_at)}
                </TableCell>
                <TableCell className="font-medium">
                  {j.state_code}
                  {j.city ? ` / ${j.city}` : ""}
                </TableCell>
                <TableCell>
                  <div className="flex items-center gap-1.5">
                    <StatusBadge value={j.status} />
                    {j.partial && <PartialBadge />}
                  </div>
                </TableCell>
                <TableCell className="text-right tabular-nums">
                  {j.completed_tiles} / {j.total_tiles}
                </TableCell>
                <TableCell className="text-right tabular-nums">
                  {j.fetched_count}
                </TableCell>
                <TableCell className="text-right tabular-nums">
                  {j.inserted_count}
                </TableCell>
                <TableCell className="text-right tabular-nums">
                  {j.updated_count}
                </TableCell>
                <TableCell className="text-right tabular-nums">
                  {j.needs_review_count}
                </TableCell>
                <TableCell className="text-right font-mono text-xs">
                  ${j.actual_cost_usd}
                </TableCell>
              </TableRow>
            ))}
            {data && data.results.length === 0 && (
              <TableRow>
                <TableCell colSpan={9} className="text-muted-foreground">
                  No sourcing jobs yet. Trigger one above.
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
        onChange={setPage}
      />
    </PageShell>
  );
}
