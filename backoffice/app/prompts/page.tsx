"use client";

import { useQuery } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { NewPromptForm } from "@/components/new-prompt-form";
import { Pagination } from "@/components/pagination";
import { PageShell } from "@/components/page-shell";
import { Card } from "@/components/ui/card";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { formatDateTime } from "@/lib/format";
import { promptsApi } from "@/lib/api";

// The prompts endpoint returns a plain (unpaginated) array, so paging is done
// client-side by slicing.
const PAGE_SIZE = 20;

export default function PromptsPage() {
  const router = useRouter();
  const [page, setPage] = useState(1);

  const { data, isLoading, error } = useQuery({
    queryKey: ["prompts"],
    queryFn: promptsApi.list,
  });

  const total = data?.length ?? 0;
  const pageCount = Math.max(1, Math.ceil(total / PAGE_SIZE));
  const rows = (data ?? []).slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE);

  return (
    <PageShell
      title="Prompts"
      description="Versioned BlandAI task prompts. One entry per prompt name."
    >
      <NewPromptForm />
      <Card>
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Name</TableHead>
              <TableHead>Versions</TableHead>
              <TableHead>Updated</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {isLoading && (
              <TableRow>
                <TableCell colSpan={3} className="text-muted-foreground">
                  Loading…
                </TableCell>
              </TableRow>
            )}
            {error && (
              <TableRow>
                <TableCell colSpan={3} className="text-destructive">
                  {(error as Error).message}
                </TableCell>
              </TableRow>
            )}
            {rows.map((p) => (
              <TableRow
                key={p.name}
                onClick={() =>
                  router.push(`/prompts/${encodeURIComponent(p.name)}`)
                }
              >
                <TableCell className="font-medium">{p.name}</TableCell>
                <TableCell>{p.version_count}</TableCell>
                <TableCell className="text-muted-foreground">
                  {formatDateTime(p.updated_at)}
                </TableCell>
              </TableRow>
            ))}
            {data && total === 0 && (
              <TableRow>
                <TableCell colSpan={3} className="text-muted-foreground">
                  No prompts yet.
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
