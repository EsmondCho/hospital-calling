import { Badge } from "@/components/ui/badge";

const VARIANT: Record<
  string,
  "default" | "secondary" | "destructive" | "outline" | "success" | "warning"
> = {
  // CallSchedule
  PENDING: "outline",
  DISPATCHED: "secondary",
  SKIPPED: "warning",
  CANCELED: "destructive",
  // CallScheduleTarget
  DIALING: "secondary",
  DONE: "success",
  // CallAttempt
  QUEUED: "outline",
  IN_PROGRESS: "secondary",
  COMPLETED: "success",
  FAILED: "destructive",
  // Hospital ownership
  INDEPENDENT: "success",
  CHAIN: "warning",
  MARS_VH: "warning",
  RETAIL_EMBEDDED: "warning",
  NONPROFIT: "secondary",
  UNIVERSITY: "secondary",
  FRANCHISE: "warning",
  UNCLASSIFIED: "outline",
  // SourcingJob status
  RUNNING: "secondary",
  CANCELLED: "destructive",
};

export function StatusBadge({ value }: { value: string | null | undefined }) {
  if (!value) return <Badge variant="outline">—</Badge>;
  return <Badge variant={VARIANT[value] ?? "outline"}>{value}</Badge>;
}

// A sourcing job is "partial" when it reached COMPLETED but some data is
// missing (DRT-5265). Partial is orthogonal to status, so it renders as its
// own badge — `warning` colour clearly separates it from a clean COMPLETED.
export function PartialBadge() {
  return <Badge variant="warning">Partial</Badge>;
}
