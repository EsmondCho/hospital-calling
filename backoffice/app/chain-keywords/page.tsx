"use client";

import { useQuery } from "@tanstack/react-query";
import { useState } from "react";

import { PageShell } from "@/components/page-shell";
import { Pagination } from "@/components/pagination";
import { ServiceTagsChips } from "@/components/service-tags-chips";
import { StatusBadge } from "@/components/status-badge";
import { Card } from "@/components/ui/card";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { chainKeywordsApi } from "@/lib/api";
import { valueOrDash } from "@/lib/timezones";

const COL_COUNT = 6;

// The chain-keywords endpoint returns a plain (unpaginated) array, so paging is
// done client-side by slicing.
const PAGE_SIZE = 20;

export default function ChainKeywordsPage() {
  const [page, setPage] = useState(1);
  const { data, isLoading, error } = useQuery({
    queryKey: ["chain-keywords"],
    queryFn: () => chainKeywordsApi.list(),
  });

  const total = data?.length ?? 0;
  const pageCount = Math.max(1, Math.ceil(total / PAGE_SIZE));
  const rows = (data ?? []).slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE);

  return (
    <PageShell
      title="Chain keywords"
      description="Rule-pass table the sourcing pipeline matches hospital names against. Read-only — edit rows in the hospcall-server Django admin console."
    >
      <Card>
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead className="w-16 text-right">Priority</TableHead>
              <TableHead>Brand</TableHead>
              <TableHead>Ownership</TableHead>
              <TableHead>Service tags</TableHead>
              <TableHead>Regex</TableHead>
              <TableHead>Notes</TableHead>
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
            {rows.map((kw) => (
              <TableRow key={kw.id}>
                <TableCell className="text-right tabular-nums text-muted-foreground">
                  {kw.match_priority}
                </TableCell>
                <TableCell className="font-medium">
                  {kw.display_name}
                  <span className="ml-2 font-mono text-xs text-muted-foreground">
                    {kw.chain_brand_normalized}
                  </span>
                </TableCell>
                <TableCell>
                  <StatusBadge value={kw.ownership} />
                </TableCell>
                <TableCell>
                  <ServiceTagsChips tags={kw.service_tags} />
                </TableCell>
                <TableCell className="font-mono text-xs">
                  {kw.regex_pattern}
                </TableCell>
                <TableCell className="text-xs text-muted-foreground">
                  {valueOrDash(kw.notes)}
                </TableCell>
              </TableRow>
            ))}
            {data && total === 0 && (
              <TableRow>
                <TableCell colSpan={COL_COUNT} className="text-muted-foreground">
                  No chain keywords yet — seed them via the Django admin.
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </Card>
      <Pagination
        page={page}
        pageCount={pageCount}
        onChange={setPage}
      />
    </PageShell>
  );
}
