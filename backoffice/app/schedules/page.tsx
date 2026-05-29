import { Suspense } from "react";

import { SchedulesList } from "./schedules-list";

// SchedulesList reads pagination state via useSearchParams, which requires a
// Suspense boundary to prerender (Next.js 16 build constraint).
export default function SchedulesPage() {
  return (
    <Suspense>
      <SchedulesList />
    </Suspense>
  );
}
