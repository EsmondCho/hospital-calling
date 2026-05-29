"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { useMemo, useState } from "react";

import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Combobox, type ComboboxOption } from "@/components/ui/combobox";
import { ApiError, type NewSourcingJob, sourcingApi } from "@/lib/api";
import { US_STATES } from "@/lib/states";

const FIELD_CLASS =
  "w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-ring";

// Server-side bounds (SPEC.md `POST /jobs/`). Left optional in the form —
// blank means "let the server apply its default".
const MAX_DEPTH_MIN = 1;
const MAX_DEPTH_MAX = 8;
const CALL_LIMIT_MIN = 1;
const CALL_LIMIT_MAX = 100;

// The server applies this max depth when the field is left blank
// (SOURCING_MAX_DEPTH) — shown as the input placeholder.
const DEFAULT_MAX_DEPTH = 6;

// The server applies this call limit when the field is left blank — used so
// the cost hint reflects what an empty submit will actually cost.
const DEFAULT_CALL_LIMIT = 50;

// Approximate per-request cost of a Google Places Text Search call on the
// Enterprise SKU. Each sourcing call maps to roughly one such request, so
// `call_limit × this` is a rough upper-bound dollar estimate.
const EST_COST_PER_CALL_USD = 0.035;

// Parse an optional bounded integer field. Returns `undefined` when blank
// (the payload omits it → server default) or out of range.
function parseOptionalInt(
  raw: string,
  lo: number,
  hi: number,
): number | undefined {
  const t = raw.trim();
  if (t === "") return undefined;
  const n = Number(t);
  if (!Number.isInteger(n) || n < lo || n > hi) return undefined;
  return n;
}

// Muted count badge shown on the right of a state row.
function StateCountBadge({ count }: { count: number }) {
  return (
    <span className="rounded bg-muted px-1.5 py-0.5 text-xs text-muted-foreground tabular-nums">
      {count.toLocaleString("en-US")}
    </span>
  );
}

// City row trailing indicator. Three visually distinct states:
//  - has hospitals       → green-ish count badge
//  - sourced, 0 hospitals → solid amber badge ("we ran a job, found nothing")
//  - never sourced       → dashed-border gray marker ("untouched")
function CityStatusIndicator({
  hospitalCount,
  sourced,
}: {
  hospitalCount: number;
  sourced: boolean;
}) {
  if (hospitalCount > 0) {
    return (
      <span className="rounded bg-emerald-100 px-1.5 py-0.5 text-xs font-medium text-emerald-700 tabular-nums dark:bg-emerald-950/40 dark:text-emerald-400">
        🏥 {hospitalCount.toLocaleString("en-US")}
      </span>
    );
  }
  if (sourced) {
    return (
      <span className="rounded bg-amber-100 px-1.5 py-0.5 text-xs font-medium text-amber-700 dark:bg-amber-950/40 dark:text-amber-400">
        Sourced · 0 found
      </span>
    );
  }
  return (
    <span className="rounded border border-dashed border-muted-foreground/40 px-1.5 py-0.5 text-xs text-muted-foreground/70">
      Not sourced
    </span>
  );
}

export function NewSourcingJobForm() {
  const router = useRouter();
  const queryClient = useQueryClient();

  const [stateCode, setStateCode] = useState<string | null>(null);
  const [city, setCity] = useState<string | null>(null);
  const [maxDepth, setMaxDepth] = useState<string>("");
  const [callLimit, setCallLimit] = useState<string>("");
  const [clientError, setClientError] = useState<string | null>(null);

  // Per-state hospital counts. Only states with ≥1 hospital come back, so a
  // lookup miss means count 0.
  const statesQuery = useQuery({
    queryKey: ["sourcing-states"],
    queryFn: sourcingApi.states,
  });

  // Cities for the selected state. Disabled until a state is picked; the key
  // includes the state so switching states refetches.
  const citiesQuery = useQuery({
    queryKey: ["sourcing-cities", stateCode],
    queryFn: () => sourcingApi.cities(stateCode as string),
    enabled: stateCode !== null,
  });

  const stateOptions = useMemo<ComboboxOption[]>(() => {
    const counts = new Map(
      (statesQuery.data ?? []).map((s) => [s.state_code, s.hospital_count]),
    );
    return US_STATES.map((s) => ({
      value: s.code,
      label: `${s.code} — ${s.name}`,
      trailing: <StateCountBadge count={counts.get(s.code) ?? 0} />,
    }));
  }, [statesQuery.data]);

  // Server already returns cities abc-sorted by name.
  const cityOptions = useMemo<ComboboxOption[]>(
    () =>
      (citiesQuery.data ?? []).map((c) => ({
        value: c.name,
        label: c.name,
        trailing: (
          <CityStatusIndicator
            hospitalCount={c.hospital_count}
            sourced={c.sourced}
          />
        ),
      })),
    [citiesQuery.data],
  );

  const cityPlaceholder = stateCode === null
    ? "Select a state first"
    : citiesQuery.isError
      ? "Failed to load cities"
      : citiesQuery.isLoading
        ? "Loading…"
        : "Select city";

  // The cost hint must mirror what submit actually bills: an out-of-range
  // or non-integer entry is rejected and the server falls back to its
  // default, so estimate against the same parsed value submit will use.
  const parsedCallLimit = parseOptionalInt(
    callLimit,
    CALL_LIMIT_MIN,
    CALL_LIMIT_MAX,
  );
  const effectiveCallLimit = parsedCallLimit ?? DEFAULT_CALL_LIMIT;
  const estCost = effectiveCallLimit * EST_COST_PER_CALL_USD;

  const mutation = useMutation({
    mutationFn: sourcingApi.create,
    onSuccess: (job) => {
      queryClient.invalidateQueries({ queryKey: ["sourcing-jobs"] });
      router.push(`/sourcing/${job.id}`);
    },
  });

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setClientError(null);

    if (stateCode === null) {
      setClientError("State is required.");
      return;
    }
    const trimmedCity = (city ?? "").trim();
    if (trimmedCity === "") {
      setClientError("City is required.");
      return;
    }

    if (maxDepth.trim() !== "") {
      const n = Number(maxDepth);
      if (!Number.isInteger(n) || n < MAX_DEPTH_MIN || n > MAX_DEPTH_MAX) {
        setClientError(
          `Max depth must be an integer between ${MAX_DEPTH_MIN} and ${MAX_DEPTH_MAX}.`,
        );
        return;
      }
    }
    if (callLimit.trim() !== "") {
      const n = Number(callLimit);
      if (!Number.isInteger(n) || n < CALL_LIMIT_MIN || n > CALL_LIMIT_MAX) {
        setClientError(
          `Call limit must be an integer between ${CALL_LIMIT_MIN} and ${CALL_LIMIT_MAX}.`,
        );
        return;
      }
    }

    const payload: NewSourcingJob = {
      state_code: stateCode,
      city: trimmedCity,
    };
    const depth = parseOptionalInt(maxDepth, MAX_DEPTH_MIN, MAX_DEPTH_MAX);
    if (depth !== undefined) payload.max_depth = depth;
    const limit = parseOptionalInt(callLimit, CALL_LIMIT_MIN, CALL_LIMIT_MAX);
    if (limit !== undefined) payload.call_limit = limit;

    mutation.mutate(payload);
  }

  return (
    <Card className="mb-4 space-y-3 p-4">
      <h2 className="text-sm font-semibold">Trigger sourcing job</h2>
      <form className="space-y-3" onSubmit={handleSubmit}>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <label htmlFor="sourcing-state" className="block space-y-1 text-sm">
            <span className="text-muted-foreground">State</span>
            <Combobox
              id="sourcing-state"
              options={stateOptions}
              value={stateCode}
              onChange={(next) => {
                setStateCode(next);
                setCity(null);
              }}
              placeholder="Select state"
              searchPlaceholder="Search states…"
              emptyText={
                statesQuery.isError
                  ? "Failed to load states."
                  : "No matching states."
              }
            />
          </label>
          <label htmlFor="sourcing-city" className="block space-y-1 text-sm">
            <span className="text-muted-foreground">City</span>
            <Combobox
              id="sourcing-city"
              options={cityOptions}
              value={city}
              onChange={setCity}
              disabled={stateCode === null}
              placeholder={cityPlaceholder}
              searchPlaceholder="Search cities…"
              emptyText={
                citiesQuery.isError
                  ? "Failed to load cities."
                  : citiesQuery.isLoading
                    ? "Loading…"
                    : "No matching cities."
              }
            />
          </label>
        </div>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <label className="block text-sm">
            <span className="text-muted-foreground">
              Max depth (optional, {MAX_DEPTH_MIN}–{MAX_DEPTH_MAX})
            </span>
            <input
              className={FIELD_CLASS}
              type="number"
              min={MAX_DEPTH_MIN}
              max={MAX_DEPTH_MAX}
              placeholder={String(DEFAULT_MAX_DEPTH)}
              value={maxDepth}
              onChange={(e) => setMaxDepth(e.target.value)}
            />
          </label>
          <label className="block text-sm">
            <span className="text-muted-foreground">
              Call limit (optional, {CALL_LIMIT_MIN}–{CALL_LIMIT_MAX})
            </span>
            <input
              className={FIELD_CLASS}
              type="number"
              min={CALL_LIMIT_MIN}
              max={CALL_LIMIT_MAX}
              placeholder={String(DEFAULT_CALL_LIMIT)}
              value={callLimit}
              onChange={(e) => setCallLimit(e.target.value)}
            />
            <span className="mt-1 block text-xs text-muted-foreground">
              Est. cost ≈ ${estCost.toFixed(2)} ({effectiveCallLimit} calls)
            </span>
          </label>
        </div>
        <div className="flex justify-end gap-2">
          <Button type="submit" disabled={mutation.isPending}>
            {mutation.isPending ? "Triggering…" : "Run"}
          </Button>
        </div>
        {clientError && (
          <p className="text-sm text-destructive">{clientError}</p>
        )}
        {mutation.error && (
          <p className="text-sm text-destructive">
            {mutation.error instanceof ApiError
              ? `${mutation.error.message} (${mutation.error.status})`
              : (mutation.error as Error).message}
          </p>
        )}
      </form>
    </Card>
  );
}
