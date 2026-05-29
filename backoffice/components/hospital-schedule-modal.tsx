"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import {
  ScheduleBatchFields,
  type ScheduleBatchValue,
  emptyScheduleBatchValue,
} from "@/components/schedule-batch-fields";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { schedulesApi, type Hospital } from "@/lib/api";

type Props = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** Hospitals checked on the list — the batch dispatch order is this order. */
  hospitals: Hospital[];
  /** Called after a successful create so the parent can clear its selection. */
  onCreated: () => void;
};

/**
 * Modal that schedules a sequential call run for the hospitals checked on the
 * Hospitals list. Reuses `ScheduleBatchFields` so the prompt/version, time,
 * voice/model and memo inputs match `NewScheduleForm` exactly.
 */
export function HospitalScheduleModal({
  open,
  onOpenChange,
  hospitals,
  onCreated,
}: Props) {
  const queryClient = useQueryClient();
  const [fields, setFields] = useState<ScheduleBatchValue>(
    emptyScheduleBatchValue()
  );
  const [timeError, setTimeError] = useState<string | null>(null);

  const mutation = useMutation({
    mutationFn: schedulesApi.create,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["schedules"] });
      setFields(emptyScheduleBatchValue());
      setTimeError(null);
      onOpenChange(false);
      onCreated();
    },
  });

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    if (hospitals.length === 0 || !fields.versionId || !fields.scheduledAt)
      return;
    if (new Date(fields.scheduledAt).getTime() <= Date.now()) {
      setTimeError("Scheduled time must be in the future.");
      return;
    }
    setTimeError(null);
    mutation.mutate({
      hospitals: hospitals.map((h) => h.id),
      prompt: Number(fields.versionId),
      scheduled_at: fields.scheduledAt,
      memo: fields.memo || null,
      voice: fields.voice || undefined,
      model: fields.model || undefined,
    });
  };

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        // Reset transient errors when the operator dismisses the modal.
        if (!next) setTimeError(null);
        onOpenChange(next);
      }}
    >
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Schedule a call batch</DialogTitle>
          <DialogDescription>
            선택한 순서대로 한 통씩 순차 발신됩니다 (이전 통화 종료 후 다음 발신).
          </DialogDescription>
        </DialogHeader>
        <form className="space-y-3" onSubmit={submit}>
          <div className="rounded-md border border-input bg-muted/40 p-2">
            <p className="text-xs font-medium text-muted-foreground">
              {hospitals.length} hospital
              {hospitals.length === 1 ? "" : "s"} selected
            </p>
            <ol className="mt-1 max-h-32 space-y-0.5 overflow-y-auto">
              {hospitals.map((h, i) => (
                <li key={h.id} className="text-sm">
                  <span className="text-muted-foreground">{i + 1}.</span>{" "}
                  {h.name}
                  {h.state ? (
                    <span className="text-muted-foreground"> ({h.state})</span>
                  ) : null}
                </li>
              ))}
            </ol>
          </div>
          <ScheduleBatchFields
            value={fields}
            onChange={setFields}
            hospitalTimezone={hospitals[0]?.timezone ?? null}
            timeError={timeError}
          />
          <DialogFooter>
            <Button
              variant="outline"
              type="button"
              onClick={() => onOpenChange(false)}
            >
              Cancel
            </Button>
            <Button
              type="submit"
              disabled={
                mutation.isPending ||
                hospitals.length === 0 ||
                !fields.versionId
              }
            >
              {mutation.isPending ? "Creating…" : "Create schedule"}
            </Button>
          </DialogFooter>
          {mutation.error && (
            <p className="text-sm text-destructive">
              {(mutation.error as Error).message}
            </p>
          )}
        </form>
      </DialogContent>
    </Dialog>
  );
}
