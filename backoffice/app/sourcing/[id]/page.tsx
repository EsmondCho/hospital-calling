"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { use, useEffect, useState } from "react";

import { PageShell } from "@/components/page-shell";
import { PartialBadge, StatusBadge } from "@/components/status-badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { API_BASE_URL } from "@/lib/config";
import {
  type SourcingJob,
  type SourcingPartialReason,
  sourcingApi,
} from "@/lib/api";
import { formatDateTime } from "@/lib/format";

const TERMINAL = new Set(["COMPLETED", "FAILED", "CANCELLED"]);

// Human-readable labels for the server's `partial_reason` codes
// (DRT-5265 §4.8.2).
const PARTIAL_REASON_LABEL: Record<SourcingPartialReason, string> = {
  call_limit: "Call limit reached",
  min_size_residual: "Minimum tile size reached — some results may be missing",
  tile_failures: "Some tiles failed after retries",
};

export default function SourcingJobDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  const queryClient = useQueryClient();

  const { data, error, isLoading } = useQuery({
    queryKey: ["sourcing-job", id],
    queryFn: () => sourcingApi.get(id),
  });

  const [streamError, setStreamError] = useState<string | null>(null);

  // Subscribe to the SSE progress stream while the job is non-terminal.
  // The cached query is the single source of truth — every frame is pushed
  // there via `setQueryData`, so the component renders from `data` only
  // (no parallel `liveJob` state to leak across navigations).
  // The effect depends on `id` and `data?.status` rather than `data` itself
  // so identity-only re-renders don't re-create the EventSource.
  const status = data?.status;
  useEffect(() => {
    if (!id || !status || TERMINAL.has(status)) return;

    const source = new EventSource(
      `${API_BASE_URL}/backoffice/sourcing/jobs/${id}/events/`,
    );
    source.onmessage = (event) => {
      try {
        const parsed = JSON.parse(event.data) as SourcingJob;
        queryClient.setQueryData(["sourcing-job", id], parsed);
      } catch (err) {
        // Server may add new event shapes later — surface in dev console
        // so a regression doesn't silently freeze the UI.
        if (process.env.NODE_ENV !== "production") {
          console.warn("sourcing.sse.parse_error", err, event.data);
        }
      }
    };
    source.addEventListener("done", () => {
      source.close();
      queryClient.invalidateQueries({ queryKey: ["sourcing-job", id] });
    });
    source.addEventListener("timeout", () => {
      setStreamError(
        "Live progress stream timed out — reload the page for the latest state.",
      );
      source.close();
    });
    source.onerror = () => {
      // EventSource auto-reconnects on transient drops; only treat a fully
      // closed connection as fatal so a hot reload / sleep / wake doesn't
      // surface a scary "disconnected" banner.
      if (source.readyState === EventSource.CLOSED) {
        setStreamError("Live progress stream disconnected.");
      }
    };

    return () => source.close();
  }, [id, status, queryClient]);

  const cancel = useMutation({
    mutationFn: () => sourcingApi.cancel(id),
    onSuccess: (job) => {
      // The backend returns the freshly cancelled row; pushing it straight
      // into the cache flips the UI to CANCELLED immediately and lets the
      // SSE effect's terminal-status guard close the stream.
      queryClient.setQueryData(["sourcing-job", id], job);
    },
  });

  if (isLoading) return <PageShell title="Sourcing job">Loading…</PageShell>;
  if (error)
    return (
      <PageShell title="Sourcing job">
        <p className="text-destructive">{(error as Error).message}</p>
      </PageShell>
    );
  if (!data) return null;

  const job = data;
  const isActive = !TERMINAL.has(job.status);

  return (
    <PageShell
      title={`Sourcing #${job.id}`}
      description={`${job.state_code}${job.city ? ` / ${job.city}` : ""}`}
      actions={
        <>
          <StatusBadge value={job.status} />
          {job.partial && <PartialBadge />}
          {isActive && (
            <Button
              variant="outline"
              size="sm"
              disabled={cancel.isPending}
              onClick={() => cancel.mutate()}
            >
              {cancel.isPending ? "Cancelling…" : "Cancel"}
            </Button>
          )}
        </>
      }
    >
      {job.partial && (
        <Card className="border-amber-300 bg-amber-50 dark:border-amber-900/60 dark:bg-amber-950/30">
          <CardContent>
            <p className="text-sm font-semibold text-amber-800 dark:text-amber-300">
              Incomplete data (partial)
            </p>
            <p className="mt-1 text-sm text-amber-700 dark:text-amber-400">
              {job.partial_reason
                ? PARTIAL_REASON_LABEL[job.partial_reason]
                : "Reason unknown"}
            </p>
            <p className="mt-2 text-xs text-amber-700 dark:text-amber-400">
              Capped tiles {job.capped_tile_count ?? 0} · Failed tiles{" "}
              {job.failed_tile_count ?? 0}
            </p>
          </CardContent>
        </Card>
      )}
      <Card>
        <CardContent>
          <dl className="grid grid-cols-[130px_1fr] gap-y-3 text-sm sm:grid-cols-[180px_1fr]">
            <Term label="Created" value={formatDateTime(job.created_at)} />
            <Term label="Started" value={formatDateTime(job.started_at)} />
            <Term label="Completed" value={formatDateTime(job.completed_at)} />
            <Term
              label="Tile progress"
              value={`${job.completed_tiles} / ${job.total_tiles}`}
            />
            <Term label="Capped tiles" value={job.capped_tile_count} />
            <Term label="Failed tiles" value={job.failed_tile_count} />
            <Term label="Google calls" value={job.call_count ?? 0} />
            <Term label="Max depth" value={job.max_depth ?? "—"} />
            <Term label="Call limit" value={job.call_limit ?? "—"} />
            <Term label="Fetched" value={job.fetched_count} />
            <Term label="Inserted" value={job.inserted_count} />
            <Term label="Updated" value={job.updated_count} />
            <Term label="Skipped (locked)" value={job.skipped_count} />
            <Term label="Excluded (rule)" value={job.excluded_count} />
            <Term label="Needs review" value={job.needs_review_count} />
            <Term label="Errors" value={job.error_count} />
            <Term label="Actual cost (USD)" value={`$${job.actual_cost_usd}`} />
            <Term label="LLM input tokens" value={job.llm_input_tokens ?? 0} />
            <Term label="LLM output tokens" value={job.llm_output_tokens ?? 0} />
            {job.error_message && (
              <Term label="Error message" value={job.error_message} />
            )}
          </dl>
        </CardContent>
      </Card>
      <Card>
        <CardContent>
          <Link
            href={`/hospitals?source=GOOGLE_PLACES`}
            className="text-sm font-medium underline-offset-4 hover:underline"
          >
            → Browse hospitals
          </Link>
        </CardContent>
      </Card>
      {streamError && (
        <p className="text-xs text-muted-foreground">{streamError}</p>
      )}
    </PageShell>
  );
}

function Term({ label, value }: { label: string; value: unknown }) {
  return (
    <>
      <dt className="text-muted-foreground">{label}</dt>
      <dd className="font-mono text-xs">
        {value == null || value === "" ? "—" : String(value)}
      </dd>
    </>
  );
}
