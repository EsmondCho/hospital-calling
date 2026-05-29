"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { use } from "react";

import { EditScheduleForm } from "@/components/edit-schedule-form";
import { PageShell } from "@/components/page-shell";
import { StatusBadge } from "@/components/status-badge";
import { Card, CardContent } from "@/components/ui/card";
import { callsApi, schedulesApi } from "@/lib/api";
import { formatDateTime } from "@/lib/format";
import { KST, formatInTimezone, valueOrDash } from "@/lib/timezones";

export default function ScheduleDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  const { data, isLoading, error } = useQuery({
    queryKey: ["schedule", id],
    queryFn: () => schedulesApi.get(id),
  });

  const calls = useQuery({
    queryKey: ["calls", { scheduleId: id }],
    queryFn: () => callsApi.list({ scheduleId: id }),
    enabled: !!data,
  });

  if (isLoading) return <PageShell title="Schedule">Loading…</PageShell>;
  if (error)
    return (
      <PageShell title="Schedule">
        <p className="text-destructive">{(error as Error).message}</p>
      </PageShell>
    );
  if (!data) return null;

  const firstTz = data.targets[0]?.hospital_timezone ?? null;

  return (
    <PageShell
      title={`Schedule #${data.id}`}
      description={data.memo ?? undefined}
      actions={<StatusBadge value={data.status} />}
    >
      <Card>
        <CardContent>
          <dl className="grid grid-cols-[110px_1fr] gap-y-3 text-sm sm:grid-cols-[160px_1fr]">
            <dt className="text-muted-foreground">Scheduled (KST)</dt>
            <dd>{formatInTimezone(data.scheduled_at, KST)}</dd>
            <dt className="text-muted-foreground">Scheduled (first hospital)</dt>
            <dd>
              {firstTz
                ? `${formatInTimezone(data.scheduled_at, firstTz)} (${firstTz})`
                : "— (hospital has no timezone)"}
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
            <dd>{data.voice}</dd>
            <dt className="text-muted-foreground">Model</dt>
            <dd>{data.model}</dd>
            <dt className="text-muted-foreground">Created</dt>
            <dd>{formatDateTime(data.created_at)}</dd>
            <dt className="text-muted-foreground">Updated</dt>
            <dd>{formatDateTime(data.updated_at ?? null)}</dd>
          </dl>
          {data.metadata && Object.keys(data.metadata).length > 0 ? (
            <pre className="mt-4 rounded-md bg-muted p-3 font-mono text-xs">
              {JSON.stringify(data.metadata, null, 2)}
            </pre>
          ) : null}
        </CardContent>
      </Card>

      <Card>
        <CardContent>
          <h2 className="mb-3 text-sm font-semibold">
            Targets ({data.hospital_count})
          </h2>
          {data.targets.length === 0 ? (
            <p className="text-sm text-muted-foreground">No targets.</p>
          ) : (
            <ol className="flex flex-col gap-2 text-sm">
              {data.targets.map((t) => (
                <li
                  key={`${t.order}-${t.hospital_id ?? "none"}`}
                  className="flex flex-wrap items-center gap-x-3 gap-y-1 rounded-md border border-input px-3 py-2"
                >
                  <span className="font-mono text-xs text-muted-foreground">
                    #{t.order}
                  </span>
                  <span className="font-medium">
                    {t.hospital_name && t.hospital_id != null ? (
                      <Link
                        href={`/hospitals/${t.hospital_id}`}
                        className="text-primary underline"
                      >
                        {t.hospital_name} ↗
                      </Link>
                    ) : (
                      "—"
                    )}
                  </span>
                  <span className="sm:ml-auto">
                    <StatusBadge value={t.status} />
                  </span>
                </li>
              ))}
            </ol>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardContent>
          <h2 className="mb-3 text-sm font-semibold">Calls</h2>
          {calls.isLoading && (
            <p className="text-sm text-muted-foreground">Loading…</p>
          )}
          {calls.error && (
            <p className="text-sm text-destructive">
              {(calls.error as Error).message}
            </p>
          )}
          {calls.data && calls.data.results.length === 0 && (
            <p className="text-sm text-muted-foreground">
              No calls yet — beat will create one when the schedule fires.
            </p>
          )}
          {calls.data && calls.data.results.length > 0 && (
            <ul className="flex flex-col gap-2 text-sm">
              {calls.data.results.map((c) => (
                <li key={c.id}>
                  <Link
                    href={`/calls/${c.id}`}
                    className="flex flex-wrap items-center gap-x-3 gap-y-1 rounded-md border border-input px-3 py-2 hover:bg-accent"
                  >
                    <span className="font-mono text-xs">#{c.id}</span>
                    <StatusBadge value={c.status} />
                    <span className="text-xs text-muted-foreground">
                      {formatDateTime(c.started_at) === "—"
                        ? `created ${formatDateTime(c.created_at)}`
                        : `started ${formatDateTime(c.started_at)}`}
                    </span>
                    <span className="text-xs text-muted-foreground sm:ml-auto">
                      {valueOrDash(c.answered_by)}
                    </span>
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>

      <EditScheduleForm schedule={data} />
    </PageShell>
  );
}
