"use client";

import { useQuery } from "@tanstack/react-query";
import { use } from "react";

import Link from "next/link";

import { CallComments } from "@/components/call-comments";
import { CallRecordingPlayer } from "@/components/call-recording-player";
import { CallStarButton } from "@/components/call-star-button";
import { DeleteCallButton } from "@/components/delete-call-button";
import { PageShell } from "@/components/page-shell";
import { StatusBadge } from "@/components/status-badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { callsApi } from "@/lib/api";
import { formatDateTime, formatDuration } from "@/lib/format";
import { valueOrDash } from "@/lib/timezones";

export default function CallDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  const { data, isLoading, error } = useQuery({
    queryKey: ["call", id],
    queryFn: () => callsApi.get(id),
  });

  if (isLoading) return <PageShell title="Call log">Loading…</PageShell>;
  if (error)
    return (
      <PageShell title="Call log">
        <p className="text-destructive">{(error as Error).message}</p>
      </PageShell>
    );
  if (!data) return null;

  return (
    <PageShell
      title={`Call log #${data.id}`}
      description={data.hospital_name ?? "Unknown hospital"}
      actions={
        <div className="flex items-center gap-2">
          <CallStarButton
            id={data.id}
            isStarred={data.is_starred}
            invalidate={[["call", String(data.id)], ["calls"]]}
          />
          <StatusBadge value={data.status} />
        </div>
      }
    >
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <Card>
          <CardHeader><CardTitle>Metadata</CardTitle></CardHeader>
          <CardContent>
            <dl className="grid grid-cols-[100px_1fr] gap-y-2 text-sm sm:grid-cols-[120px_1fr]">
              <dt className="text-muted-foreground">Status</dt>
              <dd><StatusBadge value={data.status} /></dd>
              <dt className="text-muted-foreground">Answered by</dt>
              <dd>{data.answered_by ?? "—"}</dd>
              <dt className="text-muted-foreground">Ended by</dt>
              <dd>{data.call_ended_by ?? "—"}</dd>
              <dt className="text-muted-foreground">Duration</dt>
              <dd className="font-mono text-xs">{formatDuration(data.duration_seconds)}</dd>
              <dt className="text-muted-foreground">Started</dt>
              <dd>{formatDateTime(data.started_at)}</dd>
              <dt className="text-muted-foreground">Ended</dt>
              <dd>{formatDateTime(data.ended_at)}</dd>
              <dt className="text-muted-foreground">Hospital</dt>
              <dd>
                {data.hospital_name && data.hospital_id != null ? (
                  <Link
                    href={`/hospitals/${data.hospital_id}`}
                    className="text-primary underline"
                  >
                    {data.hospital_name} ↗
                  </Link>
                ) : (
                  "—"
                )}
              </dd>
              <dt className="text-muted-foreground">Prompt</dt>
              <dd>
                {data.prompt_name && data.prompt_id != null ? (
                  <Link
                    href={`/prompts/${encodeURIComponent(data.prompt_name)}`}
                    className="text-primary underline"
                  >
                    {data.prompt_name} v{data.prompt_version} ↗
                  </Link>
                ) : (
                  "—"
                )}
              </dd>
              <dt className="text-muted-foreground">Voice</dt>
              <dd>{valueOrDash(data.voice)}</dd>
              <dt className="text-muted-foreground">Model</dt>
              <dd>{valueOrDash(data.model)}</dd>
              <dt className="text-muted-foreground">BlandAI ID</dt>
              <dd className="font-mono text-xs">{data.blandai_call_id ?? "—"}</dd>
              <dt className="text-muted-foreground">Schedule</dt>
              <dd>
                {data.schedule_id ? (
                  <Link
                    href={`/schedules/${data.schedule_id}`}
                    className="text-primary underline"
                  >
                    #{data.schedule_id} ↗
                  </Link>
                ) : (
                  "—"
                )}
              </dd>
            </dl>
            {data.failure_reason ? (
              <div className="mt-3 rounded-md bg-destructive/10 p-3 text-sm text-destructive">
                {data.failure_reason}
              </div>
            ) : null}
            <div className="mt-3">
              <div className="mb-1 text-xs text-muted-foreground">Recording</div>
              <CallRecordingPlayer callId={data.id} />
            </div>
          </CardContent>
        </Card>

        <Card className="lg:col-span-2">
          <CardHeader><CardTitle>Transcript</CardTitle></CardHeader>
          <CardContent>
            {data.summary ? (
              <div className="mb-4 rounded-md bg-muted/60 p-3 text-sm">
                <div className="mb-1 text-xs text-muted-foreground">Summary</div>
                {data.summary}
              </div>
            ) : null}
            {data.transcript && data.transcript.length > 0 ? (
              <div className="flex flex-col gap-3">
                {data.transcript.map((line, idx) => (
                  <div key={idx} className="text-sm">
                    <div className="text-xs font-medium text-muted-foreground uppercase">
                      {line.user}
                    </div>
                    <div>{line.text}</div>
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-sm text-muted-foreground">No transcript.</p>
            )}
          </CardContent>
        </Card>
      </div>
      <Card>
        <CardHeader><CardTitle>Comments</CardTitle></CardHeader>
        <CardContent>
          <CallComments callId={data.id} />
        </CardContent>
      </Card>
      <DeleteCallButton call={data} />
    </PageShell>
  );
}
