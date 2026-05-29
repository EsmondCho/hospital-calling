"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { use } from "react";

import { EditHospitalForm } from "@/components/edit-hospital-form";
import { PageShell } from "@/components/page-shell";
import { ServiceTagsChips } from "@/components/service-tags-chips";
import { StatusBadge } from "@/components/status-badge";
import { Card, CardContent } from "@/components/ui/card";
import { callsApi, hospitalsApi } from "@/lib/api";
import { formatDateTime } from "@/lib/format";
import { valueOrDash } from "@/lib/timezones";

export default function HospitalDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  const { data, isLoading, error } = useQuery({
    queryKey: ["hospital", id],
    queryFn: () => hospitalsApi.get(id),
  });

  const calls = useQuery({
    queryKey: ["calls", { hospitalId: id }],
    queryFn: () => callsApi.list({ hospitalId: id }),
    enabled: !!data,
  });

  if (isLoading) return <PageShell title="Hospital">Loading…</PageShell>;
  if (error)
    return (
      <PageShell title="Hospital">
        <p className="text-destructive">{(error as Error).message}</p>
      </PageShell>
    );
  if (!data) return null;

  return (
    <PageShell
      title={data.name}
      description={data.formatted_address ?? undefined}
      actions={<StatusBadge value={data.ownership} />}
    >
      <Card>
        <CardContent>
          <dl className="grid grid-cols-[120px_1fr] gap-y-3 text-sm sm:grid-cols-[180px_1fr]">
            <Term label="Ownership" value={data.ownership} />
            <DtDd label="Service tags">
              <ServiceTagsChips tags={data.service_tags} />
            </DtDd>
            <DtDd label="Specialty areas">
              <ServiceTagsChips tags={data.specialty_areas} />
            </DtDd>
            <Term label="Appointment mode" value={data.appointment_mode} />
            <Term label="Label locked" value={data.label_locked ? "Yes" : "No"} />
            <Term label="Phone" value={data.phone_e164} />
            <Term label="Website" value={data.website} />
            <Term label="City" value={data.city} />
            <Term label="State" value={data.state} />
            <Term label="ZIP" value={data.postal_code} />
            <Term label="Timezone" value={data.timezone} />
            <Term label="Source" value={data.source} />
            <Term label="External ID" value={data.source_external_id} />
            <Term label="Excluded reason" value={data.excluded_reason} />
            <Term label="Reviewed at" value={data.reviewed_at ?? null} />
            <Term label="Created" value={data.created_at} />
            <Term label="Updated" value={data.updated_at ?? null} />
          </dl>
        </CardContent>
      </Card>

      <Card>
        <CardContent>
          <h2 className="mb-3 text-sm font-semibold">Call attempts</h2>
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
              No call attempts to this hospital yet.
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
                    <span className="text-muted-foreground text-xs">
                      {c.started_at
                        ? `started ${formatDateTime(c.started_at)}`
                        : `created ${formatDateTime(c.created_at)}`}
                    </span>
                    {c.voice || c.model ? (
                      <span className="text-xs text-muted-foreground">
                        {[c.voice, c.model].filter(Boolean).join(" · ")}
                      </span>
                    ) : null}
                    <span
                      className="max-w-full truncate text-xs text-muted-foreground sm:ml-auto sm:max-w-[16rem]"
                      title={c.failure_reason ?? undefined}
                    >
                      {c.failure_reason
                        ? c.failure_reason
                        : valueOrDash(c.answered_by)}
                    </span>
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>

      <EditHospitalForm hospital={data} />
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

function DtDd({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <>
      <dt className="text-muted-foreground">{label}</dt>
      <dd>{children}</dd>
    </>
  );
}
