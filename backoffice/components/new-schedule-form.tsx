"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { HospitalMultiSearchInput } from "@/components/hospital-multi-search-input";
import {
  ScheduleBatchFields,
  type ScheduleBatchValue,
  emptyScheduleBatchValue,
} from "@/components/schedule-batch-fields";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { schedulesApi, type Hospital } from "@/lib/api";

export function NewScheduleForm() {
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);
  const [hospitals, setHospitals] = useState<Hospital[]>([]);
  const [fields, setFields] = useState<ScheduleBatchValue>(
    emptyScheduleBatchValue()
  );
  const [timeError, setTimeError] = useState<string | null>(null);

  const mutation = useMutation({
    mutationFn: schedulesApi.create,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["schedules"] });
      setHospitals([]);
      setFields(emptyScheduleBatchValue());
      setTimeError(null);
      setOpen(false);
    },
  });

  if (!open) {
    return (
      <div className="mb-4 flex justify-end">
        <Button onClick={() => setOpen(true)}>+ New schedule</Button>
      </div>
    );
  }

  return (
    <Card className="mb-4 space-y-3 p-4">
      <h2 className="text-sm font-semibold">Schedule a call</h2>
      <form
        className="space-y-3"
        onSubmit={(e) => {
          e.preventDefault();
          if (
            hospitals.length === 0 ||
            !fields.versionId ||
            !fields.scheduledAt
          )
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
        }}
      >
        <HospitalMultiSearchInput value={hospitals} onChange={setHospitals} />
        <p className="text-xs text-muted-foreground">
          선택한 순서대로 한 통씩 순차 발신됩니다 (이전 통화 종료 후 다음 발신).
        </p>
        <ScheduleBatchFields
          value={fields}
          onChange={setFields}
          hospitalTimezone={hospitals[0]?.timezone ?? null}
          timeError={timeError}
        />
        <div className="flex justify-end gap-2">
          <Button variant="outline" type="button" onClick={() => setOpen(false)}>
            Cancel
          </Button>
          <Button
            type="submit"
            disabled={
              mutation.isPending || hospitals.length === 0 || !fields.versionId
            }
          >
            {mutation.isPending ? "Saving…" : "Save"}
          </Button>
        </div>
        {mutation.error && (
          <p className="text-sm text-destructive">
            {(mutation.error as Error).message}
          </p>
        )}
      </form>
    </Card>
  );
}
