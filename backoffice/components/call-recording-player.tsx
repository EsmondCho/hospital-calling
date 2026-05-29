"use client";

import { useQuery } from "@tanstack/react-query";

import { callsApi } from "@/lib/api";

type Props = {
  callId: number;
};

// Plays a call's recording from a freshly-presigned S3 url. The url is fetched
// on demand (it expires) rather than read off the stored CallAttempt.
export function CallRecordingPlayer({ callId }: Props) {
  const { data, isLoading, error } = useQuery({
    queryKey: ["call-recording", callId],
    queryFn: () => callsApi.recording(callId),
  });

  if (isLoading) {
    return <p className="text-sm text-muted-foreground">Loading recording…</p>;
  }
  if (error) {
    return (
      <p className="text-sm text-destructive">{(error as Error).message}</p>
    );
  }
  if (!data?.url) {
    return (
      <p className="text-sm text-muted-foreground">No recording available.</p>
    );
  }

  return (
    <div className="space-y-2">
      <audio controls src={data.url} className="w-full" />
      <a
        href={data.url}
        target="_blank"
        rel="noreferrer"
        className="inline-block text-sm text-primary underline"
      >
        Download recording ↗
      </a>
    </div>
  );
}
