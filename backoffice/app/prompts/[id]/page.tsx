"use client";

import { useQuery } from "@tanstack/react-query";
import { use, useEffect, useState } from "react";

import { PageShell } from "@/components/page-shell";
import { PromptVersionForm } from "@/components/prompt-version-form";
import { PromptVersionList } from "@/components/prompt-version-list";
import { Card, CardContent } from "@/components/ui/card";
import { promptsApi } from "@/lib/api";

// The dynamic segment carries the prompt `name`, URL-encoded.
export default function PromptDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  const name = decodeURIComponent(id);

  const { data, isLoading, error } = useQuery({
    queryKey: ["prompt", name],
    queryFn: () => promptsApi.versions(name),
  });

  const [selectedId, setSelectedId] = useState<number | null>(null);

  // Default to the latest version (first row) once data arrives, and keep the
  // selection valid if the list changes (e.g. after creating a new version).
  useEffect(() => {
    if (!data || data.length === 0) return;
    setSelectedId((prev) =>
      prev != null && data.some((v) => v.id === prev) ? prev : data[0].id,
    );
  }, [data]);

  if (isLoading) return <PageShell title="Prompt">Loading…</PageShell>;
  if (error)
    return (
      <PageShell title="Prompt">
        <p className="text-destructive">{(error as Error).message}</p>
      </PageShell>
    );
  if (!data || data.length === 0)
    return (
      <PageShell title={name}>
        <p className="text-muted-foreground">No versions found.</p>
      </PageShell>
    );

  const latest = data[0];
  const selected = data.find((v) => v.id === selectedId) ?? latest;

  return (
    <PageShell title={latest.name}>
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-[200px_1fr]">
        <Card className="overflow-hidden p-0">
          <PromptVersionList
            versions={data}
            selectedId={selected.id}
            onSelect={setSelectedId}
          />
        </Card>
        <div className="min-w-0">
          <Card>
            <CardContent>
              <div className="mb-3 text-sm font-medium">
                v{selected.version}
              </div>
              <pre className="whitespace-pre-wrap rounded-md bg-muted p-4 font-mono text-xs leading-relaxed">
                {selected.body}
              </pre>
              {selected.notes ? (
                <div className="mt-4 text-sm">
                  <div className="text-muted-foreground">Notes</div>
                  <div className="mt-1">{selected.notes}</div>
                </div>
              ) : null}
            </CardContent>
          </Card>
          <PromptVersionForm basis={latest} />
        </div>
      </div>
    </PageShell>
  );
}
